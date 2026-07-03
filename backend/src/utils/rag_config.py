from typing import Dict, Any, Optional
from src.config import get_settings, RagSettings
from src.schemas.rag_config import NotebookRAGConfig
from loguru import logger


def merge_rag_settings(
    notebook_settings: Optional[Dict[str, Any]], 
    global_rag_settings: Optional[RagSettings] = None
) -> RagSettings:
    """
    Merge notebook-specific RAG settings with global defaults.
    
    Notebook settings override global settings. Only non-None values from notebook
    settings are applied.
    
    Args:
        notebook_settings: Dictionary from notebook.settings (can be None or empty)
        global_rag_settings: Global RAG settings (defaults to get_settings().rag)
    
    Returns:
        RagSettings object with notebook overrides applied
    """
    if global_rag_settings is None:
        global_rag_settings = get_settings().rag
    
    # Start with global settings as defaults
    merged = global_rag_settings.model_dump()
    
    if not notebook_settings:
        return RagSettings(**merged)
    
    
    try:
        notebook_config = NotebookRAGConfig(**notebook_settings)
    except Exception as e:
        logger.warning(f"Invalid notebook settings, using defaults: {e}")
        return RagSettings(**merged)
    
    # Apply notebook overrides (only non-None values)
    notebook_dict = notebook_config.model_dump(exclude_none=True)
    
    # Apply overrides to merged dict
    for key, value in notebook_dict.items():
        if key in merged:
            merged[key] = value
            logger.info(f"RAG Merge: Key={key}, Notebook Value={value} ({type(value)}) -> New Value")
        else:
            logger.warning(f"Unknown notebook setting key: {key}, ignoring")
    
    return RagSettings(**merged)


def get_policy_overrides(notebook_settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract per-notebook policy overrides for retrieval confidence thresholds."""
    if not notebook_settings:
        return {}

    try:
        notebook_config = NotebookRAGConfig(**notebook_settings)
    except Exception as e:
        logger.warning(f"Invalid notebook settings for policy overrides: {e}")
        return {}

    overrides: Dict[str, Any] = {}
    if notebook_config.min_score_threshold is not None:
        overrides["min_score_threshold"] = notebook_config.min_score_threshold
    if notebook_config.min_context_chunks is not None:
        overrides["min_context_chunks"] = notebook_config.min_context_chunks
    return overrides
