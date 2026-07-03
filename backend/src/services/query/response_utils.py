from typing import Optional, Dict, Any, List, AsyncIterator
import asyncio
from uuid import UUID
from llama_index.core.schema import QueryBundle
from llama_index.core.vector_stores.types import MetadataFilters, MetadataFilter, FilterOperator
from llama_index.core.base.response.schema import AsyncStreamingResponse
from loguru import logger

def build_query_bundle(
    query_str: str, 
    filters: Optional[Dict[str, Any]], 
    user_id: Optional[str],
    anonymous_user_id: str
) -> QueryBundle:
    """
    Build query bundle with optional metadata filters and mandatory user_id filtering.
    """
    query_bundle = QueryBundle(query_str=query_str)
    
    # Combine user_id with other filters
    combined_filters = filters.copy() if filters else {}
    
    # Add mandatory user_id filter
    if user_id:
        combined_filters['user_id'] = str(user_id)
        logger.debug(f"Applied user_id filter: {user_id}")
    else:
        # SECURITY: Fail safe to anonymous ID
        combined_filters['user_id'] = str(anonymous_user_id)
        logger.warning(f"SECURITY: No user_id provided. Defaulting to: {anonymous_user_id}")
    
    if combined_filters:
        metadata_filters = []
        for key, value in combined_filters.items():
            # Add "metadata." prefix if missing, but handle specific keys explicitly
            if key == "document_id":
                filter_key = "metadata.document_id"
            elif key == "user_id":
                filter_key = "metadata.user_id"
            elif key == "notebook_id":
                filter_key = "metadata.notebook_id"  # Explicitly handle notebook_id
            else:
                filter_key = key if key.startswith("metadata.") else f"metadata.{key}"
            
            # Handle UUIDs or other types
            if hasattr(value, 'hex'):
                filter_value = str(value)
            else:
                filter_value = value
            
            # Ensure type safety for LlamaIndex
            if isinstance(filter_value, list):
                # Convert all elements to strings (LlamaIndex expects basic types)
                # This handles List[UUID] -> List[str] conversion which fixes the Pydantic validation error
                filter_value = [str(item) for item in filter_value]
            elif not isinstance(filter_value, (str, int, float)):
                filter_value = str(filter_value)
            
            logger.debug(f"Building filter: {filter_key} = {filter_value} (type: {type(filter_value).__name__})")
            
            if isinstance(filter_value, list):
                metadata_filters.append(
                    MetadataFilter(key=filter_key, operator=FilterOperator.IN, value=filter_value)
                )
            else:
                metadata_filters.append(
                    MetadataFilter(key=filter_key, operator=FilterOperator.EQ, value=filter_value)
                )
        query_bundle.filters = MetadataFilters(filters=metadata_filters)
        filter_keys = [f.key for f in metadata_filters]
        logger.info(f"Query bundle created with {len(metadata_filters)} filters: {filter_keys}")
    else:
        logger.debug("No filters provided to build_query_bundle")
    
    return query_bundle

def extract_response_text(response: Any) -> str:
    """Extract text from various response types."""
    if hasattr(response, 'response'):
        return response.response
    elif hasattr(response, 'response_str'):
        return response.response_str
    elif hasattr(response, 'text'):
        return response.text
    else:
        try:
            return str(response)
        except Exception as e:
            logger.warning(f"Could not extract text from response: {e}")
            return ""

async def yield_response_tokens(response: Any) -> AsyncIterator[str]:
    """Abstracts the complexity of different LlamaIndex response types."""
    if isinstance(response, AsyncStreamingResponse):
        async for token in response.async_response_gen():
            yield str(token)
    elif hasattr(response, 'response_gen'):
        # Handle generic iterator
        gen = response.response_gen
        if hasattr(gen, '__anext__'):
             async for token in gen:
                yield str(token)
        else:
            # Handle sync generator in async loop
            for token in gen:
                yield str(token)
                await asyncio.sleep(0) # Yield to event loop
    else:
        # Fallback for non-streaming response object (yields once)
        yield extract_response_text(response)

def extract_contexts_from_nodes(source_nodes: List[Any]) -> List[str]:
    """Extract context strings from source nodes."""
    contexts = []
    for node in source_nodes:
        if hasattr(node, 'node') and hasattr(node.node, 'text'):
            contexts.append(node.node.text)
        elif hasattr(node, 'text'):
            contexts.append(node.text)
        elif isinstance(node, str):
            contexts.append(node)
    return contexts

def get_sources_from_response(response: Any) -> List[Dict[str, Any]]:
    """Extract standard source citations."""
    sources = []
    if hasattr(response, 'source_nodes') and response.source_nodes:
        for i, node in enumerate(response.source_nodes, 1):
            source_info = {
                'index': i,
                'text': node.node.text if hasattr(node.node, 'text') else str(node.node),
                'score': getattr(node, 'score', None),
                'metadata': getattr(node.node, 'metadata', {}) if hasattr(node, 'node') else {},
            }
            sources.append(source_info)
    return sources

def extract_citations_from_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract structured citations from sources list.
    Handles nested metadata structures automatically.

    Returns list of dicts with:
    - document_id: UUID
    - text_preview: str
    - score: float
    - page_number: Optional[int]
    - filename: Optional[str] (extracted from metadata)
    """
    citations = []
    for src in sources:
        metadata = src.get("metadata", {})

        # Handle nested metadata (common with some vector stores/LlamaIndex versions)
        if "metadata" in metadata and isinstance(metadata["metadata"], dict):
            metadata = metadata["metadata"]

        doc_id = metadata.get("document_id")
        if doc_id:
            try:
                citation = {
                    "document_id": UUID(doc_id),
                    "text_preview": src.get("text", "")[:255],
                    "score": src.get("score", 0.0),
                    "page_number": metadata.get("page_number"),
                    "filename": metadata.get("filename"),  # Extract filename from metadata
                }
                citations.append(citation)
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid document_id in citation: {doc_id}, {e}")

    return citations


def compute_confidence_metadata(
    sources: List[Dict[str, Any]],
    min_score_threshold: float = 0.10,
) -> Dict[str, Any]:
    """
    Compute aggregate confidence metrics from retrieval sources.

    Scores may be raw Qdrant similarity (~0.1–0.5) or post-rerank (~0.4–0.95).
    """
    scores = [float(s["score"]) for s in sources if s.get("score") is not None]

    if not scores:
        return {
            "max_score": 0.0,
            "avg_score": 0.0,
            "source_count": 0,
            "min_threshold": min_score_threshold,
            "level": "none",
            "label": "No sources found",
            "is_low_confidence": True,
        }

    max_score = max(scores)
    avg_score = sum(scores) / len(scores)
    source_count = len(scores)

    # Reranker-scale scores (typical when reranking is enabled)
    if max_score >= 0.75:
        level, label = "high", "High confidence"
        is_low = False
    elif max_score >= 0.55:
        level, label = "medium", "Moderate confidence"
        is_low = False
    elif max_score >= 0.35:
        level, label = "low", "Low confidence"
        is_low = True
    else:
        level, label = "very_low", "Very low confidence"
        is_low = True

    # Raw retrieval scale fallback
    if max_score < 0.35:
        passing = sum(1 for s in scores if s >= min_score_threshold)
        if passing == 0 and max_score < min_score_threshold:
            is_low = True
            level, label = "very_low", "Insufficient source relevance"

    return {
        "max_score": round(max_score, 4),
        "avg_score": round(avg_score, 4),
        "source_count": source_count,
        "min_threshold": min_score_threshold,
        "level": level,
        "label": label,
        "is_low_confidence": is_low,
    }


async def enrich_citations_with_filenames(
    citations: List[Dict[str, Any]],
    session: Any  # AsyncSession
) -> List[Dict[str, Any]]:
    """
    Enrich citations with filenames from the Document table when missing.

    This handles cases where:
    - Documents were indexed before filename was added to metadata
    - Metadata was not properly stored in vector store

    Uses batch lookup to avoid N+1 query pattern.

    Args:
        citations: List of citation dicts from extract_citations_from_sources
        session: AsyncSession for database queries

    Returns:
        Citations list with filenames populated where possible
    """
    from src.db.repositories.document import DocumentRepository
    import re

    # Detect temp file names (e.g. tmphxad5tz0.docx, tmp1a2b3c4d.pdf)
    _TEMP_FILE_PATTERN = re.compile(r'^tmp[a-z0-9_]{6,}\.\w+$', re.IGNORECASE)

    def _is_temp_filename(name: str) -> bool:
        """Check if a filename looks like a Python tempfile name."""
        return bool(_TEMP_FILE_PATTERN.match(name))

    # Find citations missing filename OR with temp-file-looking names
    missing_filename_ids = [
        cit["document_id"] for cit in citations
        if not cit.get("filename") or _is_temp_filename(cit.get("filename", ""))
    ]

    if not missing_filename_ids:
        return citations

    # Batch lookup filenames from database (single query instead of N+1)
    doc_repo = DocumentRepository(session)
    filename_map: Dict[UUID, str] = {}

    try:
        # Use batch get method for efficient single-query lookup
        documents = await doc_repo.get_many_by_ids(missing_filename_ids)
        for doc in documents:
            if doc.filename:
                filename_map[doc.id] = doc.filename
    except Exception as e:
        logger.warning(f"Batch lookup failed for citations: {e}")
        # Fallback to individual lookups only if batch fails
        for doc_id in missing_filename_ids:
            try:
                document = await doc_repo.get(doc_id)
                if document and document.filename:
                    filename_map[doc_id] = document.filename
            except Exception as e:
                logger.debug(f"Could not lookup filename for document {doc_id}: {e}")

    # Enrich citations with looked-up filenames (replaces missing or temp names)
    for citation in citations:
        current_name = citation.get("filename", "")
        if not current_name or _is_temp_filename(current_name):
            doc_id = citation["document_id"]
            if doc_id in filename_map:
                citation["filename"] = filename_map[doc_id]

    return citations
