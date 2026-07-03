"""
Vector store utility functions.
Extracted from inline logic for reusability across services.
"""
from typing import Tuple, Optional
from uuid import UUID
from loguru import logger


async def verify_notebook_indexed(notebook_id: UUID) -> Tuple[int, Optional[str]]:
    """
    Verify that notebook documents are indexed in Qdrant.
    
    This is a convenience wrapper that can be used independently of chat filters.
    
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
