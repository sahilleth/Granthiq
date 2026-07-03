from typing import Optional
from llama_index.core.retrievers import BaseRetriever, AutoMergingRetriever
from llama_index.core.llms.llm import LLM as BaseLLM
from loguru import logger

from src.config import get_settings
from src.db.vector_store import QdrantVectorStoreWrapper, get_vector_store
from src.services.retriever.hybrid import HybridRetriever
from src.services.retriever.fusion import ContextAwareQueryFusionRetriever


def get_auto_merging_retriever(
    base_retriever: BaseRetriever,
    vector_store: Optional[QdrantVectorStoreWrapper] = None,
    similarity_top_k: int = 20,  
    rerank_top_n: int = 5,  
) -> AutoMergingRetriever:
    """
    Create AutoMergingRetriever that automatically merges child nodes.
    
    Args:
        base_retriever: Base retriever (HybridRetriever)
        vector_store: Vector store instance (required for auto-merging)
        similarity_top_k: Number of nodes to retrieve initially
        rerank_top_n: Final number of nodes after merging
    
    Returns:
        AutoMergingRetriever instance
    """
    if not vector_store:
        vector_store = get_vector_store()

    auto_merging_retriever = AutoMergingRetriever(
        base_retriever=base_retriever,
        vector_store=vector_store.get_vector_store(),  
        similarity_top_k=similarity_top_k,
        rerank_top_n=rerank_top_n,
    )
    
    logger.info(
        f"Created AutoMergingRetriever: similarity_top_k={similarity_top_k}, "
        f"rerank_top_n={rerank_top_n}"
    )
    
    return auto_merging_retriever


def get_retriever(
    llm: BaseLLM,
    similarity_top_k: Optional[int] = None,
    sparse_top_k: Optional[int] = None,
    alpha: float = 0.7,
    enable_query_fusion: Optional[bool] = None,
    fusion_num_queries: Optional[int] = None,
    fusion_mode: Optional[str] = None,
    use_hierarchical: bool = False,
    auto_merge_top_k: int = 20,
    auto_merge_rerank_n: int = 5,
    use_mmr: Optional[bool] = None,
    mmr_threshold: Optional[float] = None,
) -> BaseRetriever:
    """
    Get a retriever instance using LlamaIndex's native Qdrant hybrid search.

    Optionally wraps with AutoMergingRetriever for hierarchical chunking and
    QueryFusionRetriever for query expansion and better reranking.

    Args:
        llm: LLM instance for QueryFusionRetriever query expansion (REQUIRED for thread safety)
        similarity_top_k: Number of dense vector results to retrieve
        sparse_top_k: Number of sparse vector results (defaults to similarity_top_k)
        alpha: Fusion weight for dense vs sparse (0.0-1.0, default: 0.7 favors semantic search)
               - 0.0 = sparse only (keyword search)
               - 1.0 = dense only (semantic search)
               - 0.5 = balanced fusion
        enable_query_fusion: Enable Reciprocal Rerank Fusion (default: from config)
        fusion_num_queries: Number of query variations to generate (default: from config)
                          Set to 1 to disable query expansion
        fusion_mode: Fusion algorithm mode - "reciprocal_rerank" or "rrf" (default: from config)
        use_hierarchical: Enable AutoMergingRetriever for hierarchical chunk merging
        auto_merge_top_k: Number of nodes to retrieve for auto-merging (default: 20)
        auto_merge_rerank_n: Final number of nodes after auto-merging (default: 5)

    Returns:
        BaseRetriever instance (HybridRetriever, AutoMergingRetriever, or QueryFusionRetriever wrapper)
    """
    settings = get_settings()
    top_k = similarity_top_k or settings.rag.top_k_results
    

    enable_mmr = use_mmr if use_mmr is not None else settings.rag.enable_mmr
    mmr_diversity = mmr_threshold if mmr_threshold is not None else settings.rag.mmr_diversity
    
  
    default_alpha = getattr(settings.rag, 'default_alpha', 0.7)
    alpha_value = default_alpha if alpha == 0.7 else alpha
    
 
    retrieval_top_k = auto_merge_top_k if use_hierarchical else top_k
    hybrid_retriever = HybridRetriever(
        similarity_top_k=retrieval_top_k,
        sparse_top_k=sparse_top_k or retrieval_top_k,
        alpha=alpha_value,
        use_mmr=enable_mmr,
        mmr_threshold=mmr_diversity,
    )
    
 
    if use_hierarchical:
        logger.info("Using AutoMergingRetriever for hierarchical chunk merging")
        retriever = get_auto_merging_retriever(
            hybrid_retriever,
            vector_store=None,  
            similarity_top_k=auto_merge_top_k,
            rerank_top_n=auto_merge_rerank_n,
        )
    else:
        retriever = hybrid_retriever
    
    use_fusion = enable_query_fusion if enable_query_fusion is not None else settings.rag.enable_query_fusion
    num_queries = fusion_num_queries if fusion_num_queries is not None else settings.rag.fusion_num_queries
    mode = fusion_mode or settings.rag.fusion_mode
    
    if use_fusion and num_queries > 1:
        logger.info(
            f"Wrapping HybridRetriever with ContextAwareQueryFusionRetriever: "
            f"num_queries={num_queries}, mode={mode}"
        )

        # LLM is now required - passed explicitly for thread safety
        fusion_retriever = ContextAwareQueryFusionRetriever(
            [retriever],
            similarity_top_k=top_k,
            num_queries=num_queries,
            mode=mode,
            use_async=True,
            verbose=False,
            llm=llm,
        )

        return fusion_retriever

    return retriever

