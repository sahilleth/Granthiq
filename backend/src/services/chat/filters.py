"""
Filter building utilities for chat service.
Extracted from inline logic in chat/service.py for better maintainability.
"""
import asyncio
from typing import Dict, Tuple, Optional
from uuid import UUID
from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from src.db.repositories.document import DocumentRepository
from src.utils.cache import get_filter_cache, generate_cache_key


async def build_chat_filters(
    notebook_id: UUID,
    session: AsyncSession
) -> Tuple[Dict[str, str], int, Optional[str]]:
    """
    Build filters for chat query and verify notebook indexing status.
    
    Uses caching and parallel operations for optimal performance.
    
    Args:
        notebook_id: UUID of the notebook
        session: Database session
        
    Returns:
        Tuple of (filters_dict, indexed_count, warning_message)
        - filters_dict: Dictionary with notebook_id filter (empty if no documents)
        - indexed_count: Number of chunks indexed in Qdrant for this notebook
        - warning_message: Optional warning if documents exist but aren't indexed
    """
    # Check cache first
    cache = get_filter_cache()
    cache_key = generate_cache_key("filters", str(notebook_id))
    cached_result = await cache.get(cache_key)
    
    if cached_result is not None:
        logger.debug(f"Using cached filters for notebook {notebook_id}")
        return cached_result
    
    # Parallelize document lookup and index verification
    doc_repo = DocumentRepository(session)
    
    # Run both operations concurrently
    docs_task = asyncio.create_task(doc_repo.get_by_notebook(notebook_id))
    index_task = asyncio.create_task(verify_notebook_indexed(notebook_id))
    
    # Wait for both to complete
    notebook_docs, (indexed_count, warning_message) = await asyncio.gather(
        docs_task, index_task
    )
    
    filters: Dict[str, str] = {}
    
    if notebook_docs:
        filters['notebook_id'] = str(notebook_id)
        logger.debug(f"Filtering chat search to notebook {notebook_id} with {len(notebook_docs)} documents")
    else:
        logger.warning(f"No documents found for notebook {notebook_id} - search may return empty results")
    
    result = (filters, indexed_count, warning_message)
    
    # Cache the result (short TTL since documents/index status can change)
    await cache.set(cache_key, result, ttl=10.0)
    
    return result


async def verify_notebook_indexed(notebook_id: UUID) -> Tuple[int, Optional[str]]:
    """
    Verify that notebook documents are indexed in Qdrant.
    
    Args:
        notebook_id: UUID of the notebook
        
    Returns:
        Tuple of (indexed_count, warning_message)
        - indexed_count: Number of chunks found in Qdrant
        - warning_message: Warning message if documents exist but aren't indexed
    """
    try:
        from src.db.vector_store import get_vector_store
        from qdrant_client.models import Filter as QdrantFilter, FieldCondition, MatchValue
        
        vs = get_vector_store()
        notebook_filter = QdrantFilter(
            must=[
                FieldCondition(
                    key="metadata.notebook_id",
                    match=MatchValue(value=str(notebook_id))
                )
            ]
        )
        count_result = vs.client.count(
            collection_name=vs.collection_name,
            count_filter=notebook_filter
        )
        indexed_count = count_result.count
        logger.info(f"Found {indexed_count} indexed chunks for notebook {notebook_id} in Qdrant")
        
        warning_message = None
        if indexed_count == 0:
            # Get document count from DB to provide helpful warning
            from src.db.session import async_session_factory
            from src.db.repositories.document import DocumentRepository
            
            async with async_session_factory() as session:
                doc_repo = DocumentRepository(session)
                notebook_docs = await doc_repo.get_by_notebook(notebook_id)
                if notebook_docs:
                    warning_message = (
                        f"Notebook {notebook_id} has {len(notebook_docs)} documents in DB "
                        f"but 0 indexed chunks in Qdrant. Documents may still be processing or need re-indexing."
                    )
                    logger.warning(warning_message)
        
        return indexed_count, warning_message
        
    except Exception as e:
        logger.warning(f"Could not verify Qdrant index status: {e}")
        return 0, None
