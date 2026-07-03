import re
from typing import List, Dict, Any, Optional
from loguru import logger

from src.schemas.document import DocumentChunk


def is_junk_chunk(text: str) -> bool:
    """
    Filter only ABSOLUTE garbage. Be permissive.
    
    CRITICAL: In RAG, answers are often short. Examples:
    - "The revenue was $5M." (Length: 19) - VALID
    - "Status: Active" (Length: 14) - VALID
    - "Fig 3." (Context for a chart) - VALID
    
    This function should only remove truly useless content:
    - Empty/whitespace only
    - Standalone page numbers
    - Corrupted data patterns
    
    Args:
        text: Chunk text to evaluate
        
    Returns:
        True if chunk should be filtered out (is absolute junk), False otherwise
    """
    if not text:
        return True
    
    text = text.strip()
    
    if len(text) < 15:
        return True
    
    if not text or text.isspace():
        return True    
    if re.match(r'^(Page|P\.|p\.)\s*\d+$', text, re.IGNORECASE):
        return True
    
    if text.lower() in ["nan", "null", "none", "unknown"]:
        return True
    
    return False


def _filter_junk_items(
    items: List[Any], 
    text_extractor: callable
) -> List[Any]:
    """Generic helper to filter junk items."""
    original_count = len(items)
    filtered = []
    
    for item in items:
        text = text_extractor(item)
        if not is_junk_chunk(text):
            filtered.append(item)
            
    filtered_count = len(filtered)
    
    if original_count > filtered_count:
        logger.info(
            f"Filtered {original_count - filtered_count} junk chunks "
            f"({filtered_count}/{original_count} kept)"
        )
    
    return filtered


def filter_junk_chunks(chunks: List[DocumentChunk]) -> List[DocumentChunk]:
    """
    Filter out junk chunks from a list.
    
    Args:
        chunks: List of DocumentChunk objects
        
    Returns:
        Filtered list of DocumentChunk objects
    """
    return _filter_junk_items(chunks, lambda c: c.content)


def filter_junk_chunks_dict(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter out junk chunks from a list of dictionaries.
    
    Args:
        chunks: List of dicts with 'text' or 'content' key
        
    Returns:
        Filtered list of dictionaries
    """
    return _filter_junk_items(
        chunks, 
        lambda c: c.get('text') or c.get('content', '')
    )


def calculate_chunk_quality_score(chunk_text: str) -> float:
    """
    Calculate a quality score for a chunk (0.0 to 1.0).
    
    Higher scores indicate better quality chunks.
    
    Args:
        chunk_text: Text content of the chunk
        
    Returns:
        Quality score between 0.0 and 1.0
    """
    if not chunk_text or not chunk_text.strip():
        return 0.0
    
    text = chunk_text.strip()
    length = len(text)
    
    # Base score from length (longer is generally better, up to a point)
    length_score = min(length / 500.0, 1.0)  # Normalize to 500 chars
    
    # Information density (ratio of alphabetic characters)
    alpha_chars = sum(c.isalpha() for c in text)
    density_score = alpha_chars / length if length > 0 else 0.0
    
    # Penalize if it's mostly numbers/punctuation
    numeric_punct_ratio = sum(c.isdigit() or c in '.,- ' for c in text) / length if length > 0 else 0.0
    if numeric_punct_ratio > 0.7:
        density_score *= 0.3  # Heavy penalty
    
    # Penalize if it looks like a header/section number
    if re.match(r'^\d+\.?\d*\.?\s*[A-Z][a-z\s]*$', text) and length < 100:
        density_score *= 0.2  # Heavy penalty for section headers
    
    # Combine scores
    quality_score = (length_score * 0.3) + (density_score * 0.7)
    
    return min(max(quality_score, 0.0), 1.0)


def merge_small_chunks(chunks: List[str], min_size: int = 100) -> List[str]:
    """
    Merge tiny chunks with their neighbors.
    
    Args:
        chunks: List of chunk text strings
        min_size: Minimum size for a chunk to be considered standalone
    
    Returns:
        List of merged chunks
    """
    if not chunks:
        return []
    
    merged = []
    buffer = ""
    
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        
        if len(chunk) < min_size:
            # Accumulate small chunks
            if buffer:
                buffer += "\n\n" + chunk
            else:
                buffer = chunk
        else:
            # Add buffer to current chunk if we have one
            if buffer:
                chunk = buffer.strip() + "\n\n" + chunk
                buffer = ""
            merged.append(chunk)
    
    # Don't lose the last buffer
    if buffer:
        if merged:
            merged[-1] += "\n\n" + buffer
        else:
            # If no merged chunks yet, add buffer as-is
            merged.append(buffer)
    
    return merged


def merge_small_document_chunks(
    chunks: List[DocumentChunk],
    min_size: int = 100,
    max_merged_size: int = 2000,
) -> List[DocumentChunk]:
    """
    Merge small DocumentChunk objects with their neighbors, preserving metadata.
    Keeps chunks from the same page/paragraph together when possible.
    
    Args:
        chunks: List of DocumentChunk objects
        min_size: Minimum size for a chunk to be considered standalone
        max_merged_size: Maximum size for a merged chunk
    
    Returns:
        List of merged DocumentChunk objects
    """
    if not chunks:
        return []
    
    merged_chunks: List[DocumentChunk] = []
    current_buffer: List[DocumentChunk] = []
    current_buffer_size = 0
    
    for chunk in chunks:
        chunk_text = chunk.content.strip()
        if not chunk_text:
            continue
        
        chunk_size = len(chunk_text)
        
        # Check if we should merge this chunk
        should_merge = (
            chunk_size < min_size or
            (current_buffer and _should_merge_chunks(current_buffer[-1], chunk))
        )
        
        # Check if merging would exceed max size
        would_exceed_max = (current_buffer_size + chunk_size) > max_merged_size
        
        if should_merge and not would_exceed_max:
            # Add to buffer
            current_buffer.append(chunk)
            current_buffer_size += chunk_size
        else:
            # Flush buffer if we have one
            if current_buffer:
                merged_chunk = _merge_chunk_buffer(current_buffer)
                merged_chunks.append(merged_chunk)
                current_buffer = []
                current_buffer_size = 0
            
            # Add current chunk
            if chunk_size < min_size:
                # Still small, add to new buffer
                current_buffer = [chunk]
                current_buffer_size = chunk_size
            else:
                # Large enough to stand alone
                merged_chunks.append(chunk)
    
    # Flush any remaining buffer
    if current_buffer:
        merged_chunk = _merge_chunk_buffer(current_buffer)
        merged_chunks.append(merged_chunk)
    
    # Re-index chunks
    for idx, chunk in enumerate(merged_chunks):
        chunk.chunk_index = idx
    
    logger.debug(
        f"Merged {len(chunks)} chunks into {len(merged_chunks)} chunks "
        f"({len(chunks) - len(merged_chunks)} merged)"
    )
    
    return merged_chunks


def _should_merge_chunks(chunk1: DocumentChunk, chunk2: DocumentChunk) -> bool:
    """
    Determine if two chunks should be merged based on their metadata and content.
    
    Args:
        chunk1: First chunk
        chunk2: Second chunk
    
    Returns:
        True if chunks should be merged
    """
    # Merge if they're on the same page
    if chunk1.page_number and chunk2.page_number:
        if chunk1.page_number == chunk2.page_number:
            return True
    
    # Merge if they're consecutive and small
    if chunk1.chunk_index is not None and chunk2.chunk_index is not None:
        if chunk2.chunk_index == chunk1.chunk_index + 1:
            # Check if they seem to be part of the same paragraph
            # (no double newline between them, similar metadata)
            return True
    
    return False


def _merge_chunk_buffer(buffer: List[DocumentChunk]) -> DocumentChunk:
    """
    Merge a list of DocumentChunk objects into a single chunk.
    
    Args:
        buffer: List of chunks to merge
    
    Returns:
        Merged DocumentChunk
    """
    if not buffer:
        raise ValueError("Cannot merge empty buffer")
    
    if len(buffer) == 1:
        return buffer[0]
    
    # Use metadata from the first chunk
    base_chunk = buffer[0]
    
    # Merge content with paragraph breaks
    merged_content = "\n\n".join([chunk.content.strip() for chunk in buffer if chunk.content.strip()])
    
    # Combine metadata (prefer first chunk's metadata)
    merged_metadata = dict(base_chunk.metadata or {})
    for chunk in buffer[1:]:
        if chunk.metadata:
            # Merge unique keys
            for key, value in chunk.metadata.items():
                if key not in merged_metadata:
                    merged_metadata[key] = value
    
    return DocumentChunk(
        chunk_id=base_chunk.chunk_id,
        document_id=base_chunk.document_id,
        content=merged_content,
        chunk_index=base_chunk.chunk_index,
        page_number=base_chunk.page_number,
        metadata=merged_metadata,
    )


def chunk_by_paragraphs(
    text: str,
    chunk_size: int = 1024,
    chunk_overlap: int = 200,
    min_paragraph_size: int = 50,
    max_paragraph_size: int = 3000,
) -> List[Dict[str, Any]]:
    """
    Chunk text by paragraphs, keeping paragraphs together when possible.
    Only splits paragraphs if they exceed max_paragraph_size.
    
    Args:
        text: Text to chunk
        chunk_size: Target chunk size (used when paragraphs need splitting)
        chunk_overlap: Overlap between chunks
        min_paragraph_size: Minimum size for a paragraph to be considered valid
        max_paragraph_size: Maximum size before a paragraph is split
    
    Returns:
        List of dicts with 'text' and 'metadata' keys
    """
    if not text or not text.strip():
        return []
    
    # Split into paragraphs (double newline or single newline for some formats)
    # Try double newline first (most common)
    paragraphs = re.split(r'\n\s*\n', text)
    
    # If no double newlines, try single newlines (for some PDF formats)
    if len(paragraphs) == 1:
        paragraphs = re.split(r'\n(?=[A-Z])', text)  # Split at newlines before capital letters
    
    # If still no paragraphs, treat entire text as one paragraph
    if len(paragraphs) == 1:
        paragraphs = [text]
    
    chunks: List[Dict[str, Any]] = []
    current_chunk = ""
    current_size = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para or len(para) < min_paragraph_size:
            # Skip very short paragraphs (likely headers/footers)
            continue
        
        para_size = len(para)
        
        # If paragraph fits in current chunk, add it
        if current_size + para_size + 2 <= chunk_size:  # +2 for "\n\n"
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
            current_size += para_size + 2
        else:
            # Save current chunk if it exists
            if current_chunk:
                chunks.append({"text": current_chunk, "metadata": {}})
            
            # Handle oversized paragraph
            if para_size > max_paragraph_size:
                # Split the paragraph using sentence boundaries
                para_chunks = _split_large_paragraph(para, chunk_size, chunk_overlap)
                chunks.extend([{"text": chunk, "metadata": {}} for chunk in para_chunks])
                current_chunk = ""
                current_size = 0
            else:
                # Start new chunk with this paragraph
                current_chunk = para
                current_size = para_size
    
    # Add final chunk
    if current_chunk:
        chunks.append({"text": current_chunk, "metadata": {}})
    
    return chunks


def _split_large_paragraph(
    paragraph: str,
    chunk_size: int,
    chunk_overlap: int,
) -> List[str]:
    """
    Split a large paragraph into smaller chunks at sentence boundaries.
    
    Args:
        paragraph: Paragraph text to split
        chunk_size: Target chunk size
        chunk_overlap: Overlap between chunks
    
    Returns:
        List of chunk strings
    """
    # Split by sentences (period, exclamation, question mark followed by space)
    sentences = re.split(r'([.!?]\s+)', paragraph)
    
    # Recombine sentences with their punctuation
    combined_sentences = []
    for i in range(0, len(sentences) - 1, 2):
        if i + 1 < len(sentences):
            combined_sentences.append(sentences[i] + sentences[i + 1])
        else:
            combined_sentences.append(sentences[i])
    
    if len(sentences) % 2 == 1:
        combined_sentences.append(sentences[-1])
    
    chunks = []
    current_chunk = ""
    current_size = 0
    
    for sentence in combined_sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        sentence_size = len(sentence)
        
        if current_size + sentence_size + 1 <= chunk_size:  # +1 for space
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
            current_size += sentence_size + 1
        else:
            # Save current chunk
            if current_chunk:
                chunks.append(current_chunk)
            
            # Start new chunk with overlap
            if chunks and chunk_overlap > 0:
                # Take last few words from previous chunk for overlap
                prev_words = current_chunk.split()[-chunk_overlap // 10:]  # Approximate
                overlap_text = " ".join(prev_words)
                current_chunk = overlap_text + " " + sentence if overlap_text else sentence
                current_size = len(current_chunk)
            else:
                current_chunk = sentence
                current_size = sentence_size
    
    # Add final chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


__all__ = [
    "is_junk_chunk",
    "filter_junk_chunks",
    "filter_junk_chunks_dict",
    "calculate_chunk_quality_score",
    "merge_small_chunks",
    "merge_small_document_chunks",
    "chunk_by_paragraphs",
]

