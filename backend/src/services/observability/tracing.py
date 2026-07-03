from typing import Dict, Any, Optional, List
from loguru import logger
from langfuse import propagate_attributes
from src.services.observability.langfuse_config import  get_langfuse_client

def trace_synthesis(
    query: str,
    response_length: int,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Optional[Any]:
    """
    Trace a response synthesis operation.
    """
    langfuse = get_langfuse_client()
    if not langfuse:
        return None
    
    try:
        synthesis_metadata: Dict[str, Any] = {
            "query": query,
            "response_length": response_length,
            "operation": "synthesis",
            **(metadata or {}),
        }
        if tags:
            synthesis_metadata["tags"] = (tags or []) + ["synthesis"]
        
        with langfuse.start_as_current_observation(
            as_type="span",
            name="synthesis",
            metadata=synthesis_metadata,
        ) as span:
            with propagate_attributes(user_id=user_id, session_id=session_id):
                return span
            
    except Exception as e:
        logger.warning(f"Failed to trace synthesis: {e}")
        return None


def trace_embedding(
    text_count: int,
    embedding_dim: int,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Optional[Any]:
    """
    Trace an embedding generation operation.
    """
    langfuse = get_langfuse_client()
    if not langfuse:
        return None
    
    try:
        embedding_metadata: Dict[str, Any] = {
            "text_count": text_count,
            "embedding_dim": embedding_dim,
            "operation": "embedding",
            **(metadata or {}),
        }
        if tags:
            embedding_metadata["tags"] = (tags or []) + ["embedding"]
        
        with langfuse.start_as_current_observation(
            as_type="span",
            name="embedding",
            metadata=embedding_metadata,
        ) as span:
            with propagate_attributes(user_id=user_id, session_id=session_id):
                return span
            
    except Exception as e:
        logger.warning(f"Failed to trace embedding: {e}")
        return None


def log_evaluation_scores(
    scores: Dict[str, float],
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    comment: Optional[str] = None,
) -> None:
    """
    Log RAGAS evaluation scores to Langfuse.
    """
    langfuse = get_langfuse_client()
    if not langfuse:
        logger.warning("Langfuse client not available, skipping score logging")
        return
    
    try:
        for metric_name, score_value in scores.items():
            if score_value is None or (isinstance(score_value, float) and str(score_value) == 'nan'):
                continue
            
            score_name = f"ragas_{metric_name}"
            
            try:
                if hasattr(langfuse, 'create_score'):
                    langfuse.create_score(
                        name=score_name,
                        value=float(score_value),
                        trace_id=trace_id,
                        observation_id=span_id,
                        comment=comment or f"RAGAS {metric_name} score",
                    )
                elif hasattr(langfuse, 'score'):
                    langfuse.score(
                        name=score_name,
                        value=float(score_value),
                        trace_id=trace_id,
                        observation_id=span_id,
                        comment=comment or f"RAGAS {metric_name} score",
                    )
            except Exception as score_error:
                logger.warning(f"Failed to log score {metric_name}: {score_error}")
                continue
                
    except Exception as e:
        logger.error(f"Failed to log evaluation scores to Langfuse: {e}")
