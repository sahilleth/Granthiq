from typing import Optional
import os

from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.postprocessor.cohere_rerank import CohereRerank
from loguru import logger

from src.config import get_settings


def create_reranker(
    reranker_type: Optional[str] = None,
    model_name: Optional[str] = None,
    top_n: Optional[int] = None,
    cohere_api_key: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> Optional[BaseNodePostprocessor]:
    """
    Create a Cohere reranker instance for fast API-based reranking.
    
    REMOVED: SentenceTransformerRerank (local transformer-based reranking)
    REASON: Adds significant latency. Cohere API is faster and more efficient.
    
    Args:
        reranker_type: Type of reranker (must be 'cohere', kept for compatibility)
        model_name: Cohere model name (ignored, uses rerank-english-v3.0)
        top_n: Number of top results to return after reranking
        cohere_api_key: Cohere API key (required)
        enabled: Explicitly enable/disable reranking (overrides global setting)
        
    Returns:
        CohereRerank instance, or None if disabled or API key missing
    """
    settings = get_settings()
    
    reranker_type = reranker_type or settings.rag.reranker_type
    top_n = top_n or settings.rag.reranker_top_n
    cohere_api_key = cohere_api_key or os.getenv("COHERE_API_KEY") or getattr(settings.llm, 'cohere_api_key', None)

    # Treat unset/placeholder keys as missing. A placeholder like
    # "your_cohere_api_key_here" is a truthy string, so without this check the
    # reranker would be built and then fail every query with a 401 from Cohere,
    # breaking chat entirely instead of gracefully skipping reranking.
    if cohere_api_key:
        _normalized = cohere_api_key.strip().lower()
        if (
            not _normalized
            or _normalized.startswith("your_")
            or _normalized.endswith("_here")
            or "changeme" in _normalized
            or _normalized in {"none", "null", "placeholder"}
        ):
            cohere_api_key = None

    # Check enabled status: argument > global setting
    should_enable = enabled if enabled is not None else settings.rag.enable_reranking
    
    if not should_enable:
        # logger.debug("Reranking is disabled") # Noisy
        return None
    
    if reranker_type != "cohere":
        logger.warning(
            f"Reranker type '{reranker_type}' is not supported. "
            f"Only 'cohere' is supported. Falling back to Cohere."
        )
    
    if not cohere_api_key:
        logger.warning(
            "COHERE_API_KEY is not set (or is a placeholder). "
            "Skipping reranking — set a valid COHERE_API_KEY to enable it."
        )
        return None
    
    try:
        reranker = CohereRerank(
            api_key=cohere_api_key,
            model="rerank-english-v3.0",
            top_n=top_n,
        )
        # logger.info(f"Initialized CohereRerank (fast API-based): model=rerank-english-v3.0, top_n={top_n}")
        return reranker
        
    except ImportError:
        logger.error(
            "llama-index-postprocessor-cohere-rerank is not installed. "
            "Install it with: pip install llama-index-postprocessor-cohere-rerank"
        )
        return None
    except Exception as e:
        logger.error(f"Failed to initialize CohereRerank: {e}")
        return None


_reranker_instance: Optional[BaseNodePostprocessor] = None


def get_reranker(
    reranker_type: Optional[str] = None,
    model_name: Optional[str] = None,
    top_n: Optional[int] = None,
    cohere_api_key: Optional[str] = None,
    reset: bool = False,
    enabled: Optional[bool] = None,
) -> Optional[BaseNodePostprocessor]:
    """
    Get or create Cohere reranker instance.
    
    If custom parameters (top_n, enabled, etc.) are provided, it creates a NEW instance
    to serve the specific request without modifying the global singleton.
    
    Args:
        reranker_type: Type of reranker (must be 'cohere', kept for compatibility)
        model_name: Model name (ignored, uses rerank-english-v3.0)
        top_n: Number of top results
        cohere_api_key: Cohere API key (required)
        reset: Force create new instance (useful for testing)
        enabled: Explicitly enable/disable reranking
        
    Returns:
        CohereRerank instance, or None if disabled or API key missing
    """
    global _reranker_instance
    
    # If using custom settings, bypass singleton to avoid state pollution/racing
    if top_n is not None or enabled is not None or cohere_api_key is not None:
        return create_reranker(
            reranker_type=reranker_type,
            model_name=model_name,
            top_n=top_n,
            cohere_api_key=cohere_api_key,
            enabled=enabled
        )
    
    if _reranker_instance is None or reset:
        _reranker_instance = create_reranker(
            reranker_type=reranker_type,
            model_name=model_name,
            top_n=top_n,
            cohere_api_key=cohere_api_key,
            enabled=None # Use global defaults
        )
    
    return _reranker_instance
