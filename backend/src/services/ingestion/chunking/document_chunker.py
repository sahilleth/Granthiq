from typing import List, Optional, Literal
from llama_index.core import Document as LIDocument

from src.schemas.document import UnifiedDocument, DocumentChunk
from src.services.ingestion.chunking.chunk_quality import (
    filter_junk_chunks,
    merge_small_document_chunks,
)
from src.services.ingestion.chunking.splitters import get_advanced_splitter
from src.services.ingestion.chunking.metadata import clean_metadata_for_chunking
from src.services.ingestion.chunking.engine import chunk_text, subchunk_if_needed


def _build_li_document(doc: UnifiedDocument) -> LIDocument:
    """
    Create a LlamaIndex Document from UnifiedDocument concatenated text.
    """
    # Prefer existing chunks content if present; otherwise filename placeholder
    text = "\n\n".join([c.content for c in doc.chunks]) if doc.chunks else ""
    metadata = {
        "filename": doc.filename,
        "source_type": doc.source_type.value,
        **(doc.metadata or {}),
    }
    cleaned_metadata = clean_metadata_for_chunking(metadata)
    return LIDocument(text=text, metadata=cleaned_metadata)


def chunk_unified_document(
    doc: UnifiedDocument,
    *,
    chunk_size: int = 1024,
    chunk_overlap: int = 200,
    respect_sentence_boundary: bool = True,
    strategy: Literal["semantic", "token", "sentence", "markdown", "code", "auto", "hierarchical"] = "auto",
    embed_model=None,
    hierarchical_chunk_sizes: Optional[List[int]] = None,
) -> List[DocumentChunk]:
    """
    Produce DocumentChunk list from a UnifiedDocument using advanced chunking.
    """
    # Build LI document from current content
    li_doc = _build_li_document(doc)
    if not li_doc.text or not li_doc.text.strip():
        return []

    # Get appropriate splitter
    splitter = get_advanced_splitter(
        strategy=strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embed_model=embed_model,
        source_type=doc.source_type.value,
        filename=doc.filename,
        hierarchical_chunk_sizes=hierarchical_chunk_sizes,
    )
    
    nodes = splitter.get_nodes_from_documents([li_doc])

    out_chunks: List[DocumentChunk] = []
    for idx, node in enumerate(nodes):
        node_text = node.get_content()
        node_meta = dict(node.metadata or {})
        page_num = node_meta.get("page_number") or node_meta.get("page_label")
        tmp = DocumentChunk(
            chunk_id="temp",
            document_id=doc.id,
            content=node_text,
            chunk_index=idx,
            page_number=page_num,
            metadata=node_meta,
        )
        out_chunks.append(tmp)
    
    # Merge then Filter
    out_chunks = merge_small_document_chunks(
        out_chunks,
        min_size=200,
        max_merged_size=chunk_size * 2,
    )
    
    out_chunks = filter_junk_chunks(out_chunks)
    
    # Re-index chunks
    for idx, chunk in enumerate(out_chunks):
        chunk.chunk_index = idx
    
    return out_chunks


def apply_chunking_to_document(
    doc: UnifiedDocument,
    *,
    chunk_size: int = 1024,
    chunk_overlap: int = 200,
    respect_sentence_boundary: bool = True,
    strategy: Literal["semantic", "token", "sentence", "markdown", "code", "auto", "hierarchical"] = "auto",
    embed_model=None,
    hierarchical_chunk_sizes: Optional[List[int]] = None,
) -> UnifiedDocument:
    """
    In-place chunking: clears existing chunks and re-populates using advanced chunking.
    """
    base_text = "\n\n".join([c.content for c in doc.chunks]) if doc.chunks else ""
    if not base_text.strip():
        return doc

    pieces = chunk_text(
        base_text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        respect_sentence_boundary=respect_sentence_boundary,
        strategy=strategy,
        embed_model=embed_model,
        source_type=doc.source_type.value,
        filename=doc.filename,
        hierarchical_chunk_sizes=hierarchical_chunk_sizes,
        metadata={
            "filename": doc.filename,
            "source_type": doc.source_type.value,
            **(doc.metadata or {}),
        },
    )

    doc.chunks = []
    for idx, p in enumerate(pieces):
        page_num = p["metadata"].get("page_number") or p["metadata"].get("page_label")
        doc.add_chunk(
            content=p["text"],
            chunk_index=idx,
            page_number=page_num,
            metadata=p["metadata"],
        )
    return doc


def chunk_unified_document_non_destructive(
    doc: UnifiedDocument,
    *,
    chunk_size: int = 1024,
    chunk_overlap: int = 200,
    respect_sentence_boundary: bool = True,
    strategy: Literal["semantic", "token", "sentence", "markdown", "code", "auto", "hierarchical"] = "auto",
    embed_model=None,
    hierarchical_chunk_sizes: Optional[List[int]] = None,
) -> List[DocumentChunk]:
    """
    Hierarchical, structure-preserving chunking.
    Returns a NEW list of DocumentChunk objects (non-mutating).
    """
    if not doc.chunks:
        return []

    final_chunks: List[DocumentChunk] = []
    chunk_counter = 0

    for base_chunk in doc.chunks:
        text = (base_chunk.content or "").strip()
        if not text:
            continue

        metadata = {
            **(base_chunk.metadata or {}),
            "filename": doc.filename,
            "source_type": doc.source_type.value,
            "document_id": doc.id,
        }

        subchunks = subchunk_if_needed(
            text,
            metadata=metadata,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            respect_sentence_boundary=respect_sentence_boundary,
            strategy=strategy,
            embed_model=embed_model,
            source_type=doc.source_type.value,
            filename=doc.filename,
        )

        for _sub_idx, sub in enumerate(subchunks):
            final_chunks.append(
                DocumentChunk(
                    chunk_id=f"{doc.id}_{chunk_counter}",
                    document_id=doc.id,
                    content=sub["text"],
                    chunk_index=chunk_counter,
                    page_number=metadata.get("page_number"),
                    metadata=sub["metadata"],
                )
            )
            chunk_counter += 1

    final_chunks = filter_junk_chunks(final_chunks)
    
    final_chunks = merge_small_document_chunks(
        final_chunks,
        min_size=150,
        max_merged_size=chunk_size * 2,
    )
    
    for idx, chunk in enumerate(final_chunks):
        chunk.chunk_index = idx

    return final_chunks


def apply_chunking_to_document_non_destructive(
    doc: UnifiedDocument,
    *,
    chunk_size: int = 1024,
    chunk_overlap: int = 200,
    respect_sentence_boundary: bool = True,
    strategy: Literal["semantic", "token", "sentence", "markdown", "code", "auto", "hierarchical"] = "auto",
    embed_model=None,
    hierarchical_chunk_sizes: Optional[List[int]] = None,
) -> UnifiedDocument:
    """
    Replace a document's chunks with a structure-preserving, sub-chunked version.
    """
    new_chunks = chunk_unified_document_non_destructive(
        doc,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        respect_sentence_boundary=respect_sentence_boundary,
        strategy=strategy,
        embed_model=embed_model,
        hierarchical_chunk_sizes=hierarchical_chunk_sizes,
    )

    doc.chunks = new_chunks
    return doc

