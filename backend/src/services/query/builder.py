from typing import Optional
from llama_index.core.query_engine import RetrieverQueryEngine, TransformQueryEngine, BaseQueryEngine
from llama_index.core.response_synthesizers import ResponseMode, get_response_synthesizer
from llama_index.core.postprocessor import MetadataReplacementPostProcessor
from llama_index.core.llms.llm import LLM as BaseLLM
from loguru import logger

from src.config import get_settings
from src.utils.query_utils import _map_response_mode
from src.services.retriever.retriever import get_retriever
from src.services.llm.factory import create_llamaindex_llm
from src.services.llm.llamaindex_prompts import get_prompt_templates, get_tree_summarize_template
from src.services.reranker.reranker import get_reranker
from src.evaluation.ragas_evaluator import get_ragas_evaluator
from src.services.query.policy import CertaintyPostProcessor
from src.services.query.safe_hyde import SafeHyDEQueryTransform
from src.services.query.filter_preserving_engine import FilterPreservingQueryEngine
from src.services.query.source_numbering import SourceNumberingPostProcessor

class QueryEngineBuilder:
    """
    Builder for constructing a QueryEngineService with valid components.
    Encapsulates the complexity of setting up LLMs, Retrievers, Synthesizers, etc.
    """
    
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        
        self.llm: Optional[BaseLLM] = None
        self.retriever = None
        self.synthesizer = None
        self.node_postprocessors = []
        self.query_engine: Optional[BaseQueryEngine] = None
        self.evaluator = None
        
        self.provider = self.settings.llm.provider
        self.streaming = self.settings.rag.streaming
        self.use_hyde = self.settings.rag.use_hyde
        
    def with_llm(self, provider: Optional[str] = None) -> "QueryEngineBuilder":
        """Configure the Main LLM."""
        provider = provider or self.provider
        api_key = getattr(self.settings.llm, f'{provider}_api_key', None)
        
        if not api_key:
            logger.warning(f"API key for {provider} not found.")
        
        # Use provider-appropriate model if model_name is default Gemini model
        model_name = self.settings.llm.model_name
        if provider == "groq" and model_name == "gemini-2.5-flash":
            # Use a good Groq model for chat (fast and high quality)
            model_name = "llama-3.3-70b-versatile"
            logger.info(f"Using Groq model: {model_name} for chat")
        elif provider == "groq" and not model_name.startswith("llama") and not model_name.startswith("groq/"):
            # Auto-select good Groq model if generic model name
            model_name = "llama-3.3-70b-versatile"
            
        self.llm = create_llamaindex_llm(
            provider=provider,
            api_key=api_key,
            model=model_name,
            temperature=self.settings.llm.temperature,
            max_tokens=self.settings.llm.max_tokens,
        )
        # Note: LLM is passed explicitly to all components (retriever, synthesizer, etc.)
        # We do NOT set Settings.llm globally to maintain thread safety under concurrent requests
        self.provider = provider 
        return self

    def with_retriever(
        self, 
        similarity_top_k: Optional[int] = None,
        enable_query_fusion: Optional[bool] = None,
        fusion_num_queries: Optional[int] = None,
        hybrid_alpha: Optional[float] = None
    ) -> "QueryEngineBuilder":
        """Configure the Retriever."""
        if not self.llm:
            self.with_llm()    
        alpha_val = hybrid_alpha if hybrid_alpha is not None else self.settings.rag.default_alpha
        f_num = fusion_num_queries if fusion_num_queries is not None else (2 if self.use_hyde else 4)
        
        self.retriever = get_retriever(
            llm=self.llm,  # Required first parameter for thread safety
            similarity_top_k=similarity_top_k,
            enable_query_fusion=enable_query_fusion,
            fusion_num_queries=f_num,
            use_mmr=self.settings.rag.enable_mmr,
            mmr_threshold=self.settings.rag.mmr_diversity,
            alpha=alpha_val,
        )
        return self

    def with_synthesizer(
        self, 
        response_mode: Optional[ResponseMode] = None,
        streaming: Optional[bool] = None,
        prompt_style: Optional[str] = None
    ) -> "QueryEngineBuilder":
        """Configure the Response Synthesizer."""
        if not self.llm:
            self.with_llm()

        self.streaming = streaming if streaming is not None else self.streaming
        style_to_use = prompt_style if prompt_style is not None else self.settings.rag.prompt_style
        
        if response_mode:
            mapped_mode = _map_response_mode(response_mode)
        else:
            mapped_mode = _map_response_mode(self.settings.rag.response_mode)

        kwargs = {
            "llm": self.llm,
            "response_mode": mapped_mode,
            "streaming": self.streaming,
        }
        prompts = get_prompt_templates(prompt_style=style_to_use, include_citations=True)
        
        if mapped_mode in [ResponseMode.COMPACT, ResponseMode.COMPACT_ACCUMULATE]:
            kwargs["text_qa_template"] = prompts["text_qa_template"]
        elif mapped_mode == ResponseMode.REFINE:
            kwargs["text_qa_template"] = prompts["text_qa_template"]
            kwargs["refine_template"] = prompts["refine_template"]
        elif mapped_mode in [ResponseMode.TREE_SUMMARIZE, ResponseMode.SIMPLE_SUMMARIZE]:
            kwargs["summary_template"] = get_tree_summarize_template(prompt_style=style_to_use)
            kwargs["use_async"] = True

        self.synthesizer = get_response_synthesizer(**kwargs)
        return self


    def with_postprocessors(
        self,
        reranker_top_n: Optional[int] = None,
        enable_reranking: Optional[bool] = None,
        policy_min_score: Optional[float] = None,
        policy_min_chunks: Optional[int] = None,
        policy_disabled: bool = False,
    ) -> "QueryEngineBuilder":
        """
        Configure Postprocessors (Reranker, Policy, etc).
        
        Args:
            reranker_top_n: Number of top results to rerank
            enable_reranking: Explicitly enable/disable reranking
            policy_min_score: Override policy min_score_threshold (for evaluation)
            policy_min_chunks: Override policy min_context_chunks (for evaluation)
            policy_disabled: If True, disable policy filtering entirely (for evaluation)
        """
        processors = []
        if self.settings.rag.use_sentence_window:
            processors.append(MetadataReplacementPostProcessor(target_metadata_key="window"))
        
        r_top = reranker_top_n if reranker_top_n is not None else self.settings.rag.reranker_top_n
        reranker = get_reranker(top_n=r_top, enabled=enable_reranking)
        if reranker:
            processors.append(reranker)
        
        # Create policy postprocessor with optional overrides for evaluation
        processors.append(CertaintyPostProcessor(
            min_score_threshold=policy_min_score,
            min_context_chunks=policy_min_chunks,
            disabled=policy_disabled
        ))
        
        # CRITICAL: Add source numbering LAST so LLM sees [Source 1], [Source 2], etc.
        # This enables correct inline citations like [1], [2] in responses
        processors.append(SourceNumberingPostProcessor(include_metadata=True))
            
        self.node_postprocessors = processors
        return self

    def with_evaluator(self) -> "QueryEngineBuilder":
        """Configure Online Evaluator."""
        if self.settings.evaluation.enabled and self.settings.evaluation.online_evaluation:
            try:
                self.evaluator = get_ragas_evaluator()
            except Exception as e:
                logger.warning(f"Failed to initialize RAGAS evaluator: {e}")
        return self

    def _setup_fast_llm(self) -> BaseLLM:
        """Internal helper for HyDE LLM."""
        if self.settings.llm.groq_api_key:
            # HyDE only needs a short hypothetical passage. Reserving the full
            # llm.max_tokens (8192) counts against Groq's per-minute token limit
            # (free tier TPM=6000) and gets every request rejected with a
            # RateLimitError, silently breaking chat. Cap the output small.
            return create_llamaindex_llm(
                provider="groq",
                api_key=self.settings.llm.groq_api_key,
                model="llama-3.1-8b-instant",
                temperature=0.7,
                max_tokens=512,
            )
        
        return self.llm

    def build(self, use_hyde: Optional[bool] = None) -> BaseQueryEngine:
        """Construct the final Query Engine with filter preservation."""

        if not self.llm: self.with_llm()
        if not self.retriever: self.with_retriever()
        if not self.synthesizer: self.with_synthesizer()

        base_engine = RetrieverQueryEngine(
            retriever=self.retriever,
            response_synthesizer=self.synthesizer,
            node_postprocessors=self.node_postprocessors,
        )

        hyde_enabled = use_hyde if use_hyde is not None else self.use_hyde

        if hyde_enabled:
            logger.info("Enabling Fast HyDE with Groq")
            fast_llm = self._setup_fast_llm()

            hyde = SafeHyDEQueryTransform(include_original=True, llm=fast_llm)

            transform_engine = TransformQueryEngine(base_engine, query_transform=hyde)

            # CRITICAL: Wrap with FilterPreservingQueryEngine to prevent filter loss through HyDE
            self.query_engine = FilterPreservingQueryEngine(transform_engine)
            logger.info("Query engine wrapped with FilterPreservingQueryEngine to preserve filters through HyDE")
        else:
            # Even without HyDE, wrap for consistent filter handling
            self.query_engine = FilterPreservingQueryEngine(base_engine)
            logger.info("Query engine wrapped with FilterPreservingQueryEngine for consistent filter handling")

        return self.query_engine

