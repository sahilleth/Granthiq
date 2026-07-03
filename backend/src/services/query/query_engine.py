import hashlib
from typing import Optional, List, Dict, Any, AsyncIterator
import random
import asyncio

from llama_index.core.response_synthesizers import ResponseMode
from llama_index.core.base.response.schema import Response, AsyncStreamingResponse
from loguru import logger

from src.config import get_settings, RagSettings
from src.services.observability.tracing import log_evaluation_scores
from src.services.query.response_utils import (
    build_query_bundle,
    yield_response_tokens,
    extract_response_text,
    extract_contexts_from_nodes,
    get_sources_from_response
)
from src.services.query.tracing_utils import trace_context
from src.services.query.builder import QueryEngineBuilder
from src.services.reranker.reranker import get_reranker
from src.utils.query_utils import _map_response_mode
from src.utils.cache import get_query_result_cache, get_query_embedding_cache, generate_cache_key


def _generate_query_cache_key(query_str: str, filters: Optional[Dict], user_id: Optional[str]) -> str:
    """Generate cache key for query results."""
    filter_str = str(sorted(filters.items())) if filters else ""
    key_data = f"{query_str}|{filter_str}|{user_id or ''}"
    return hashlib.sha256(key_data.encode()).hexdigest()[:32]
class QueryEngineService:
    """
    Query engine service using LlamaIndex RetrieverQueryEngine.
    Refactored to use QueryEngineBuilder for modular construction.
    """
    
    def __init__(
        self,
        llm_provider: Optional[str] = None,
        response_mode: Optional[ResponseMode] = None,
        streaming: Optional[bool] = None,
        prompt_style: Optional[str] = None,
        similarity_top_k: Optional[int] = None,
        enable_query_fusion: Optional[bool] = None,
        fusion_num_queries: Optional[int] = None,
        use_hyde: Optional[bool] = None,
        hybrid_alpha: Optional[float] = None,
        reranker_top_n: Optional[int] = None,
        enable_reranking: Optional[bool] = None,
        policy_min_score: Optional[float] = None,
        policy_min_chunks: Optional[int] = None,
        policy_disabled: bool = False,
    ):
        """
        Initialize query engine service.
        
        Args:
            policy_min_score: Override policy min_score_threshold (for evaluation)
            policy_min_chunks: Override policy min_context_chunks (for evaluation)
            policy_disabled: If True, disable policy filtering entirely (for evaluation)
        """
        self.settings = get_settings()
        # Note: setup_langfuse() is called once at app startup (see app.py)

        builder = QueryEngineBuilder(self.settings)
        
        builder.with_llm(llm_provider)
        builder.with_retriever(
            similarity_top_k=similarity_top_k,
            enable_query_fusion=enable_query_fusion,
            fusion_num_queries=fusion_num_queries,
            hybrid_alpha=hybrid_alpha
        )
        builder.with_synthesizer(
            response_mode=response_mode,
            streaming=streaming,
            prompt_style=prompt_style
        )
        builder.with_postprocessors(
            reranker_top_n=reranker_top_n,
            enable_reranking=enable_reranking,
            policy_min_score=policy_min_score,
            policy_min_chunks=policy_min_chunks,
            policy_disabled=policy_disabled
        )
        builder.with_evaluator()
        
        
        self.query_engine = builder.build(use_hyde=use_hyde)
        
        self.provider = builder.provider
        self.llm = builder.llm
        self.retriever = builder.retriever
        self.streaming = builder.streaming
        self._evaluator = builder.evaluator
        self._last_streaming_response = None
        
        logger.info(
            f"QueryEngineService ready: provider={self.provider}, "
            f"streaming={self.streaming}, hyde={use_hyde if use_hyde is not None else builder.use_hyde}"
        )

    def query(self, query_str: str, filters: Optional[Dict[str, Any]] = None):
        """Synchronous query wrapper."""
        query_bundle = build_query_bundle(
            query_str, filters, None, self.settings.anonymous_user_id
        )
        return self.query_engine.query(query_bundle)

    async def aquery(
        self,
        query_str: str,
        filters: Optional[Dict] = None,
        user_id: str = None,
        session_id: str = None
    ):
        """Unified asynchronous query method with caching."""
        # Check cache first (skip cache for streaming or if explicitly disabled)
        cache = get_query_result_cache()
        cache_key = _generate_query_cache_key(query_str, filters, user_id)
        
        cached_result = await cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Query cache hit for: {query_str[:50]}...")
            return cached_result
        
        query_bundle = build_query_bundle(
            query_str, filters, user_id, self.settings.anonymous_user_id
        )

        # CRITICAL: Validate filters were applied
        if hasattr(query_bundle, 'filters') and query_bundle.filters:
            filter_keys = [f.key for f in query_bundle.filters.filters] if hasattr(query_bundle.filters, 'filters') else []
            logger.info(f"QueryEngineService.aquery: QueryBundle has {len(filter_keys)} filters: {filter_keys}")
        else:
            logger.error(f"QueryEngineService.aquery: QueryBundle has NO filters! This is a BUG - filters were: {filters}")

        model_name = getattr(self.llm, "model", None)

        async with trace_context("rag_query", query_str, filters, user_id, session_id, model=model_name) as ctx:
            # CRITICAL: Store filters on retriever BEFORE calling aquery
            # This ensures filters can be recovered if lost during QueryFusionRetriever operations
            if hasattr(query_bundle, 'filters') and query_bundle.filters:
                if hasattr(self.query_engine, '_engine') and hasattr(self.query_engine._engine, 'retriever'):
                    retriever = self.query_engine._engine.retriever
                    retriever._preserved_filters = query_bundle.filters
                    logger.debug(f"Stored filters on retriever before query execution")
            
            # Pass filters explicitly as kwargs to ensure they reach the retriever
            logger.debug(f"Calling query_engine.aquery with QueryBundle(filters={query_bundle.filters})")
            response = await self.query_engine.aquery(query_bundle)
            

            if not getattr(response, "source_nodes", []):
                logger.info("Policy: No valid nodes found. Returning refusal.")
                refusal_msg = self.settings.policy.refusal_message
                
                refusal_response = Response(
                    response=refusal_msg,
                    source_nodes=[],
                    metadata={"policy_refusal": True}
                )
                # Cache refusal responses briefly
                await cache.set(cache_key, refusal_response, ttl=10.0)
                return refusal_response

            if isinstance(response, AsyncStreamingResponse):
                full_text = ""
                async for token in response.async_response_gen():
                    full_text += token
                
                response = Response(
                    response=full_text,
                    source_nodes=response.source_nodes,
                    metadata=response.metadata
                )
            
            response_text = extract_response_text(response)
            ctx["response_text"] = response_text
            ctx["metadata"] = {
                "provider": self.provider,
                "source_nodes_count": len(response.source_nodes) if hasattr(response, 'source_nodes') else 0
            }
            
            # Cache the successful response
            await cache.set(cache_key, response)
            
            self._trigger_eval(query_str, response, ctx.get('trace_id'))
            return response

    async def stream_query(
        self, 
        query_str: str, 
        filters: Optional[Dict] = None, 
        user_id: str = None, 
        session_id: str = None
    ) -> AsyncIterator[str]:
        """
        Unified streaming query method.
        """
        query_bundle = build_query_bundle(
            query_str, filters, user_id, self.settings.anonymous_user_id
        )
        
        full_text_arr = []

        model_name = getattr(self.llm, "model", None)

        async with trace_context("rag_stream_query", query_str, filters, user_id, session_id, model=model_name) as ctx:
            streaming_response = await self.query_engine.aquery(query_bundle)
            
        
            if not getattr(streaming_response, "source_nodes", []):
                 logger.info("Policy: No valid nodes found. Aborting stream.")
                 yield self.settings.policy.refusal_message
                 return

            self._last_streaming_response = streaming_response # Store for access
            
            # Iterate using helper
            async for token in yield_response_tokens(streaming_response):
                full_text_arr.append(token)
                yield token
            
            # Finalize Trace Data
            full_text = "".join(full_text_arr)
            ctx["response_text"] = full_text
            ctx["metadata"] = {
                "provider": self.provider,
                "source_nodes_count": len(streaming_response.source_nodes) if hasattr(streaming_response, 'source_nodes') else 0
            }
            
            # Trigger Background Eval
            self._trigger_eval(query_str, streaming_response, ctx.get('trace_id'))

    # ======================== AUXILIARY METHODS ========================

    def _trigger_eval(self, query: str, response: Any, trace_id: Optional[str]):
        """Fire-and-forget evaluation."""
        if (self._evaluator and 
            random.random() < self.settings.evaluation.evaluation_sampling_rate):
            asyncio.create_task(
                self._evaluate_response_async(query, response, trace_id, None)
            )

    async def _evaluate_response_async(
        self, query_str: str, response: Any, trace_id: str, span_id: str
    ):
        """Internal async evaluation logic."""
        try:
            answer = extract_response_text(response)
            source_nodes = getattr(response, 'source_nodes', [])
            contexts = extract_contexts_from_nodes(source_nodes)
            
            if not answer or not contexts: return

            scores = await self._evaluator.evaluate_single(
                question=query_str, answer=answer, contexts=contexts
            )
            
            if scores and self.settings.evaluation.log_scores_to_langfuse:
                log_evaluation_scores(scores, trace_id, span_id, "RAGAS online evaluation")
                logger.debug(f"RAGAS evaluation scores: {scores}")
        except Exception as e:
            logger.error(f"Eval Error: {e}")

    def get_last_response(self):
        return getattr(self, '_last_streaming_response', None)

    def get_sources(self, response) -> List[Dict[str, Any]]:
        return get_sources_from_response(response)

    @classmethod
    def from_rag_settings(
        cls,
        rag_settings: RagSettings,
        stream: Optional[bool] = None,
        llm_provider: Optional[str] = None,
        policy_min_score: Optional[float] = None,
        policy_min_chunks: Optional[int] = None,
    ) -> "QueryEngineService":
        """
        Create QueryEngineService from RagSettings (merged notebook settings).
        
        Args:
            rag_settings: RagSettings object (from merge_rag_settings)
            stream: Override streaming setting (optional)
            llm_provider: Override LLM provider (optional)
            policy_min_score: Per-notebook min score threshold override
            policy_min_chunks: Per-notebook min context chunks override
        
        Returns:
            QueryEngineService instance configured with the provided settings
        """
        settings = get_settings()
        
        response_mode = None
        if rag_settings.response_mode:
            response_mode = _map_response_mode(rag_settings.response_mode)
        
        service = cls(
            llm_provider=llm_provider,
            response_mode=response_mode,
            streaming=stream if stream is not None else rag_settings.streaming,
            prompt_style=rag_settings.prompt_style,
            similarity_top_k=rag_settings.top_k_results,
            enable_query_fusion=rag_settings.enable_query_fusion,
            fusion_num_queries=rag_settings.fusion_num_queries,
            use_hyde=rag_settings.use_hyde,
            hybrid_alpha=rag_settings.default_alpha,
            reranker_top_n=rag_settings.reranker_top_n,
            enable_reranking=rag_settings.enable_reranking,
            policy_min_score=policy_min_score,
            policy_min_chunks=policy_min_chunks,
        )
        
        service._rag_settings = rag_settings
        
        return service


# Singleton instance management
_query_engine_instance: Optional[QueryEngineService] = None

def get_query_engine(
    llm_provider: Optional[str] = None,
    response_mode: Optional[ResponseMode] = None,
    streaming: Optional[bool] = None,
    similarity_top_k: Optional[int] = None,
    enable_query_fusion: Optional[bool] = None,
    fusion_num_queries: Optional[int] = None,
    use_hyde: Optional[bool] = None,
    hybrid_alpha: Optional[float] = None,
    reranker_top_n: Optional[int] = None,
    policy_min_score: Optional[float] = None,
    policy_min_chunks: Optional[int] = None,
    reset: bool = False,
) -> QueryEngineService:
    global _query_engine_instance
    if _query_engine_instance is None or reset:
        if reset:
            get_reranker(reset=True)
        _query_engine_instance = QueryEngineService(
            llm_provider, response_mode, streaming, similarity_top_k, 
            enable_query_fusion, fusion_num_queries, use_hyde, hybrid_alpha, reranker_top_n,
            policy_min_score, policy_min_chunks
        )
    return _query_engine_instance
