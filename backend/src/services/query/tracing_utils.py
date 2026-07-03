from typing import Dict, Any, Optional, AsyncIterator
from contextlib import asynccontextmanager
from loguru import logger

from src.services.observability.langfuse_config import get_langfuse_client
from src.services.observability.tracing import trace_synthesis
from langfuse import propagate_attributes

@asynccontextmanager
async def trace_context(
    name: str, 
    query_str: str, 
    filters: Optional[Dict], 
    user_id: Optional[str], 
    session_id: Optional[str],
    model: Optional[str] = None
) -> AsyncIterator[Dict[str, Any]]:
    """
    Unified context manager that handles Langfuse Logic.
    Returns a result_container dict that caller should populate.
    """
    langfuse = get_langfuse_client()
    
    result_container = {"response_text": "", "metadata": {}}

    try:
        if langfuse:
            with langfuse.start_as_current_observation(
                as_type="span",
                name=name,
                model=model,
                input={"query": query_str, "filters": filters},
                metadata={"tags": ["query", "rag"]},
            ) as span:
                with propagate_attributes(
                    user_id=str(user_id) if user_id else None, 
                    session_id=str(session_id) if session_id else None
                ):
                    yield result_container

                
                span.update(output={
                    "response": result_container.get("response_text", ""), 
                    "metadata": result_container.get("metadata", {})
                })
                
                langfuse.update_current_trace(
                    input={"query": query_str, "filters": filters},
                    output={
                        "response": result_container.get("response_text", ""),
                        "metadata": result_container.get("metadata", {})
                    },
                    user_id=str(user_id) if user_id else None,
                    session_id=str(session_id) if session_id else None,
                )
                
                if result_container.get("response_text"):
                    trace_synthesis(
                        query=query_str,
                        response_length=len(result_container["response_text"]),
                        metadata=result_container.get("metadata", {}),
                        user_id=user_id,
                        session_id=session_id,
                    )
                
                trace_id = langfuse.get_current_trace_id()
                if trace_id:
                    result_container['trace_id'] = trace_id
        else:
            with propagate_attributes(
                user_id=str(user_id) if user_id else None, 
                session_id=str(session_id) if session_id else None
            ):
                yield result_container

    except Exception as e:
        logger.error(f"Query Error in trace_context: {e}")
        raise
