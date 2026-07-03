from typing import List, Dict, Any, Literal, Optional
from llama_index.core import Document as LIDocument
from loguru import logger

from src.services.ingestion.chunking.chunk_quality import chunk_by_paragraphs, filter_junk_chunks_dict
from src.services.ingestion.chunking.splitters import get_advanced_splitter
from src.services.ingestion.chunking.metadata import clean_metadata_for_chunking


def _build_li_document_from_text(
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> LIDocument:
    """
    Create a LlamaIndex Document safely from text and metadata.
    Cleans metadata to prevent size issues.
    """
    cleaned_metadata = clean_metadata_for_chunking(metadata)
    return LIDocument(text=text.strip(), metadata=cleaned_metadata)


def chunk_text(
    text: str,
    *,
    chunk_size: int = 1024,
    chunk_overlap: int = 200,
    respect_sentence_boundary: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
    strategy: Literal["semantic", "token", "sentence", "markdown", "code", "auto", "hierarchical"] = "sentence",
    embed_model=None,
    source_type: Optional[str] = None,
    filename: Optional[str] = None,
    hierarchical_chunk_sizes: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Chunk raw text using advanced or basic chunking strategies.
    """
    if not text or not text.strip():
        return []

    # Get appropriate splitter based on strategy
    splitter = get_advanced_splitter(
        strategy=strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embed_model=embed_model,
        source_type=source_type,
        filename=filename,
        hierarchical_chunk_sizes=hierarchical_chunk_sizes,
    )
    
    cleaned_metadata = clean_metadata_for_chunking(metadata)
    li_doc = LIDocument(text=text, metadata=cleaned_metadata)
    nodes = splitter.get_nodes_from_documents([li_doc])

    results: List[Dict[str, Any]] = []
    for node in nodes:
        node_text = node.get_content()
        node_meta = dict(node.metadata or {})
        results.append({"text": node_text, "metadata": node_meta})
    
    # Filter out junk chunks
    results = filter_junk_chunks_dict(results)
    
    return results


def subchunk_if_needed(
    content: str,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    chunk_size: int = 1024,
    chunk_overlap: int = 200,
    respect_sentence_boundary: bool = True,
    strategy: Literal["semantic", "token", "sentence", "markdown", "code", "auto", "paragraph", "hierarchical"] = "sentence",
    embed_model=None,
    source_type: Optional[str] = None,
    filename: Optional[str] = None,
    use_paragraph_chunking: bool = True,
    hierarchical_chunk_sizes: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Subdivide a single chunk only if it exceeds `chunk_size`.
    Preserves metadata from the parent chunk.
    Uses paragraph-aware chunking when possible to keep paragraphs together.
    """
    if not content or not content.strip():
        return []

    if len(content) <= chunk_size:
        return [{"text": content, "metadata": metadata or {}}]

    # Use paragraph-aware chunking if enabled and content seems paragraph-structured
    if use_paragraph_chunking and ("\n\n" in content or "\n" in content):
        # Check if content has paragraph-like structure
        has_paragraph_structure = (
            content.count("\n\n") >= 1 or  # Has double newlines
            (content.count("\n") >= 3 and len(content) > 500)  # Has multiple single newlines
        )
        
        if has_paragraph_structure:
            logger.debug("Using paragraph-aware chunking for better structure preservation")
            para_chunks = chunk_by_paragraphs(
                content,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                min_paragraph_size=50,
                max_paragraph_size=chunk_size * 2,  # Allow paragraphs up to 2x chunk_size before splitting
            )
            # Add metadata to each chunk
            for chunk in para_chunks:
                chunk["metadata"] = {**(metadata or {}), **(chunk.get("metadata", {}))}
            return para_chunks

    # For subchunking, prefer sentence splitting unless explicitly requested
    if strategy == "auto":
        strategy = "sentence"
    
    splitter = get_advanced_splitter(
        strategy=strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embed_model=embed_model,
        source_type=source_type,
        filename=filename,
    )

    li_doc = _build_li_document_from_text(content, metadata)
    nodes = splitter.get_nodes_from_documents([li_doc])

    return [{"text": n.get_content(), "metadata": dict(n.metadata or {})} for n in nodes]

