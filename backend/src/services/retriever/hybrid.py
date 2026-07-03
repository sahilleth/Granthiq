import hashlib
from typing import List, Optional, Dict, Any
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.vector_stores.types import (
    MetadataFilters,
    MetadataFilter,
    FilterOperator,
)
from loguru import logger
from langfuse import observe

from src.db.vector_store import QdrantVectorStoreWrapper, get_vector_store
from src.services.observability.langfuse_config import get_langfuse_client
from src.services.ingestion.chunking.chunk_quality import is_junk_chunk
from src.utils.filter import filter_low_quality_results, deduplicate_retrieved_nodes
from src.utils.cache import get_query_result_cache, generate_cache_key


def _generate_retrieval_cache_key(
    query_str: str,
    filters: Optional[MetadataFilters],
    top_k: int,
    alpha: float
) -> str:
    """Generate cache key for retrieval results."""
    filter_str = ""
    if filters and hasattr(filters, 'filters'):
        filter_parts = []
        for f in filters.filters:
            filter_parts.append(f"{f.key}:{f.value}")
        filter_str = "|".join(sorted(filter_parts))
    
    key_data = f"{query_str}|{filter_str}|{top_k}|{alpha}"
    return hashlib.sha256(key_data.encode()).hexdigest()[:32]


class HybridRetriever(BaseRetriever):
    """
    Hybrid retriever using LlamaIndex's native Qdrant hybrid search.
    
    This uses Qdrant's built-in sparse+dense vector fusion, which is:
    - Faster: Single query instead of two separate queries
    - More efficient: No need to load nodes into memory
    - Production-ready: Server-side fusion in Qdrant
    
    Features:
    - Semantic similarity search (dense vectors)
    - Keyword search (sparse vectors via BM42 - faster than BM25)
    - Automatic fusion using LlamaIndex's QdrantVectorStore
    - Metadata filtering
    """
    
    def __init__(
        self,
        vector_store: Optional[QdrantVectorStoreWrapper] = None,
        similarity_top_k: int = 10,
        sparse_top_k: Optional[int] = None,
        alpha: float = 0.7,
        use_mmr: bool = False,
        mmr_threshold: float = 0.5,
    ):
        """
        Initialize hybrid retriever using LlamaIndex's native Qdrant hybrid search.
        
        Args:
            vector_store: QdrantVectorStoreWrapper instance. If None, uses singleton.
            similarity_top_k: Number of dense vector results
            sparse_top_k: Number of sparse vector results (defaults to similarity_top_k)
            alpha: Weight for dense vs sparse fusion (0.0 = sparse only, 1.0 = dense only)
            use_mmr: Enable Maximum Marginal Relevance for diversity (uses vector_store_query_mode="mmr")
            mmr_threshold: MMR diversity threshold (0.0 = no diversity, 1.0 = max diversity)
        """
        super().__init__()
        self.vector_store = vector_store or get_vector_store()
        self.similarity_top_k = similarity_top_k
        self.sparse_top_k = sparse_top_k or similarity_top_k
        self.alpha = alpha
        self.use_mmr = use_mmr
        self.mmr_threshold = mmr_threshold
        
        self.index = self.vector_store.get_index()
        
        logger.info(
            f"HybridRetriever initialized (LlamaIndex native): "
            f"dense_top_k={similarity_top_k}, sparse_top_k={self.sparse_top_k}, alpha={alpha}, "
            f"mmr={'enabled' if use_mmr else 'disabled'}"
        )
    
    @observe(as_type="retriever")
    def _retrieve(
        self,
        query_bundle: QueryBundle,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ) -> List[NodeWithScore]:
        """
        Retrieve nodes using LlamaIndex's native Qdrant hybrid search.
        Decorated with @observe for automatic Langfuse tracing.
        Includes caching for repeated queries.
        """
        
        if not user_id and hasattr(query_bundle, "filters") and query_bundle.filters:
            for f in query_bundle.filters.filters:
                if f.key == "metadata.user_id" or f.key == "user_id":
                    user_id = str(f.value)
                    break

        # Check cache for repeated queries
        cache = get_query_result_cache()
        cache_key = _generate_retrieval_cache_key(
            query_bundle.query_str,
            getattr(query_bundle, 'filters', None),
            self.similarity_top_k,
            self.alpha
        )
        
        # Try to get from cache (note: this is sync context, so we check but don't await)
        # The cache is designed for async, but retrieval is sync in LlamaIndex
        # We'll integrate caching at the async query layer instead
      
        langfuse = get_langfuse_client()
        if langfuse:
            langfuse.update_current_span(
                name="hybrid_retrieval",
                metadata={
                    "query": query_bundle.query_str,
                    "similarity_top_k": self.similarity_top_k,
                    "sparse_top_k": self.sparse_top_k,
                    "alpha": self.alpha,
                    "use_mmr": self.use_mmr
                }
            )
           
            if user_id:
                langfuse.update_current_trace(user_id=user_id, session_id=session_id)

        # CRITICAL: Debug filter passthrough
        logger.debug(f"HybridRetriever._retrieve called with QueryBundle: {type(query_bundle).__name__}")
        logger.debug(f"QueryBundle attributes: {dir(query_bundle)}")
        logger.debug(f"QueryBundle.filters exists: {hasattr(query_bundle, 'filters')}")
        logger.debug(f"QueryBundle.filters value: {getattr(query_bundle, 'filters', 'ATTRIBUTE_MISSING')}")

        retrieve_top_k = max(self.similarity_top_k * 2, 50)
        retriever_filters = getattr(query_bundle, 'filters', None)

        # Check for preserved filters (from FilterPreservingQueryEngine)
        if not retriever_filters and hasattr(self, '_preserved_filters'):
            retriever_filters = self._preserved_filters
            if retriever_filters:
                filter_keys = [f.key for f in retriever_filters.filters] if hasattr(retriever_filters, 'filters') else []
                logger.info(f"HybridRetriever: Recovered {len(filter_keys)} filters from FilterPreservingQueryEngine: {filter_keys}")
                
        # Also check for _filters (standard LlamaIndex attribute)
        if not retriever_filters and hasattr(self, '_filters') and self._filters:
            retriever_filters = self._filters

        if retriever_filters:
            # Log filter details
            filter_keys = [f.key for f in retriever_filters.filters] if hasattr(retriever_filters, 'filters') else []
            logger.info(f"HybridRetriever: Using {len(filter_keys)} filters: {filter_keys}")
        else:
            logger.error(
                f"CRITICAL BUG: HybridRetriever received NO filters! "
                f"QueryBundle has 'filters' attr: {hasattr(query_bundle, 'filters')}, "
                f"QueryBundle.filters value: {retriever_filters}, "
                f"QueryBundle type: {type(query_bundle).__name__}"
            )

        if self.use_mmr:
            retriever = self.index.as_retriever(
                vector_store_query_mode="mmr",
                similarity_top_k=retrieve_top_k,
                sparse_top_k=retrieve_top_k,
                alpha=self.alpha,
                vector_store_kwargs={"mmr_threshold": self.mmr_threshold},
                filters=retriever_filters,
            )
        else:
            retriever = self.index.as_retriever(
                similarity_top_k=retrieve_top_k,  
                sparse_top_k=retrieve_top_k,
                alpha=self.alpha,
                filters=retriever_filters,
            )
        
        nodes = retriever.retrieve(query_bundle)
        original_count = len(nodes)
        
       
        nodes = deduplicate_retrieved_nodes(nodes)
        dedup_count = len(nodes)
        
      
        quality_nodes = filter_low_quality_results(
            nodes, 
            min_score=0.0001,
            min_chunk_length=10,
            adaptive=False,
        )
        filtered_count = len(quality_nodes)
        
      
        if langfuse:
            junk_count = sum(1 for n in nodes if is_junk_chunk(n.node.text))
            
            langfuse.update_current_span(
                metadata={
                    "retrieved_count": original_count,
                    "deduplicated_count": dedup_count,
                    "filtered_count": filtered_count,
                    "junk_chunks_retrieved": junk_count,
                    "quality_filtered": dedup_count - filtered_count,
                }
            )

        if filtered_count == 0:
            logger.warning(
                f"No chunks retrieved for query: {query_bundle.query_str[:50]}... "
                f"Original count: {original_count}, after dedup: {dedup_count}"
            )
            
        return quality_nodes
    
    def custom_retrieve(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
        sparse_top_k: Optional[int] = None,
        alpha: Optional[float] = None,
    ) -> List[NodeWithScore]:
        """
        Convenience method for direct retrieval.
        
        Args:
            query: Query string
            filters: Optional metadata filters
            top_k: Number of dense results (overrides default)
            sparse_top_k: Number of sparse results (overrides default)
            alpha: Fusion weight (overrides default)
            
        Returns:
            List of NodeWithScore objects
        """
       
        if self.use_mmr:
            retriever = self.index.as_retriever(
                vector_store_query_mode="mmr",
                similarity_top_k=top_k or self.similarity_top_k,
                sparse_top_k=sparse_top_k or self.sparse_top_k,
                alpha=alpha or self.alpha,
                vector_store_kwargs={"mmr_threshold": self.mmr_threshold},
            )
        else:
            retriever = self.index.as_retriever(
                similarity_top_k=top_k or self.similarity_top_k,
                sparse_top_k=sparse_top_k or self.sparse_top_k,
                alpha=alpha or self.alpha,
            )
        
        # Build query bundle with filters if provided
        query_bundle = QueryBundle(query_str=query)
        if filters:
            metadata_filters = []
            for key, value in filters.items():
               
                filter_key = key if key.startswith("metadata.") else f"metadata.{key}"
                
                if isinstance(value, list):
                    metadata_filters.append(
                        MetadataFilter(
                            key=filter_key,
                            operator=FilterOperator.IN,
                            value=value,
                        )
                    )
                else:
                    metadata_filters.append(
                        MetadataFilter(
                            key=filter_key,
                            operator=FilterOperator.EQ,
                            value=value,
                        )
                    )
            query_bundle.filters = MetadataFilters(filters=metadata_filters)
        
        return retriever.retrieve(query_bundle)
