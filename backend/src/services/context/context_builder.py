from typing import List, Dict, Any, Optional, Callable
from llama_index.core.schema import NodeWithScore
from loguru import logger
from contextlib import contextmanager


def build_context_string(
    nodes: List[NodeWithScore],
    max_chunks: Optional[int] = None,
    include_metadata: bool = True,
    include_scores: bool = False,
    separator: str = "\n\n",
) -> str:
    """
    Build a context string from retrieved nodes.
    
    Args:
        nodes: List of NodeWithScore objects
        max_chunks: Maximum number of chunks to include (None = all)
        include_metadata: Whether to include metadata headers
        include_scores: Whether to include similarity scores
        separator: Separator between chunks
        
    Returns:
        Formatted context string
    """
    if not nodes:
        return ""
    
    # Limit chunks if specified
    selected_nodes = nodes[:max_chunks] if max_chunks else nodes
    
    parts = []
    for i, node_score in enumerate(selected_nodes, 1):
        node = node_score.node
        text = node.text or node.get_content() if hasattr(node, 'get_content') else ""
        
        if not text:
            continue
        
        # Build header with metadata
        header_parts = []
        
        if include_metadata:
            metadata = node.metadata or {}
            
            # Add source information
            source = metadata.get("source") or metadata.get("file_name") or metadata.get("url")
            if source:
                header_parts.append(f"Source: {source}")
            
            # Add document ID
            doc_id = metadata.get("document_id")
            if doc_id:
                header_parts.append(f"Document ID: {doc_id}")
            
            # Add page/chunk number
            page = metadata.get("page_number")
            chunk_idx = metadata.get("chunk_index")
            if page is not None:
                header_parts.append(f"Page: {page}")
            elif chunk_idx is not None:
                header_parts.append(f"Chunk: {chunk_idx}")
            
            # Add date if available
            date = metadata.get("date") or metadata.get("created_at")
            if date:
                header_parts.append(f"Date: {date}")
        
        # Add score if requested
        if include_scores and node_score.score is not None:
            header_parts.append(f"Score: {node_score.score:.4f}")
        
        # Build header
        if header_parts:
            header = f"[{i}] " + " | ".join(header_parts)
            parts.append(f"{header}\n{text}")
        else:
            parts.append(f"[{i}]\n{text}")
    
    return separator.join(parts)


def build_context_with_citations(
    nodes: List[NodeWithScore],
    max_chunks: Optional[int] = None,
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Build context string with citation metadata.
    
    Args:
        nodes: List of NodeWithScore objects
        max_chunks: Maximum number of chunks to include
        
    Returns:
        Tuple of (context_string, citations_list)
        citations_list contains dicts with: index, text, metadata, score
    """
    if not nodes:
        return "", []
    
    selected_nodes = nodes[:max_chunks] if max_chunks else nodes
    
    parts = []
    citations = []
    
    for i, node_score in enumerate(selected_nodes, 1):
        node = node_score.node
        text = node.text or node.get_content() if hasattr(node, 'get_content') else ""
        
        if not text:
            continue
        
        metadata = node.metadata or {}
        
        # Build citation info
        citation = {
            "index": i,
            "text": text[:200] + "..." if len(text) > 200 else text,  # Truncate for citation
            "metadata": {
                "source": metadata.get("source") or metadata.get("file_name") or metadata.get("url"),
                "document_id": metadata.get("document_id"),
                "page_number": metadata.get("page_number"),
                "chunk_index": metadata.get("chunk_index"),
            },
            "score": node_score.score,
        }
        citations.append(citation)
        
        # Build context part
        header_parts = [f"[{i}]"]
        if citation["metadata"]["source"]:
            header_parts.append(f"Source: {citation['metadata']['source']}")
        if citation["metadata"]["page_number"] is not None:
            header_parts.append(f"Page: {citation['metadata']['page_number']}")
        
        header = " ".join(header_parts)
        parts.append(f"{header}\n{text}")
    
    context = "\n\n".join(parts)
    return context, citations


def truncate_context(
    context: str,
    max_tokens: int,
    token_estimator: Optional[Callable[[str], int]] = None,
) -> str:
    """
    Truncate context to fit within token limit.
    
    Args:
        context: Context string to truncate
        max_tokens: Maximum tokens allowed
        token_estimator: Function to estimate tokens (text) -> int.
                        If None, uses simple char-based estimation (4 chars = 1 token)
        
    Returns:
        Truncated context string
    """
    if not token_estimator:
        # Simple estimation: ~4 characters per token
        estimated_tokens = len(context) // 4
        if estimated_tokens <= max_tokens:
            return context
        
        # Truncate to approximately max_tokens
        max_chars = max_tokens * 4
        return context[:max_chars] + "\n\n[... context truncated ...]"
    
    # Use provided token estimator
    current_tokens = token_estimator(context)
    if current_tokens <= max_tokens:
        return context
    
    # Binary search for optimal truncation point
    low, high = 0, len(context)
    best_context = ""
    
    while low < high:
        mid = (low + high) // 2
        truncated = context[:mid]
        tokens = token_estimator(truncated)
        
        if tokens <= max_tokens:
            best_context = truncated
            low = mid + 1
        else:
            high = mid
    
    return best_context + "\n\n[... context truncated ...]"


def format_context_for_prompt(
    context: str,
    question: str,
    system_instruction: Optional[str] = None,
) -> str:
    """
    Format context and question into a prompt.
    
    Args:
        context: Retrieved context string
        question: User question
        system_instruction: Optional system instruction
        
    Returns:
        Formatted prompt string
    """
    parts = []
    
    if system_instruction:
        parts.append(system_instruction)
        parts.append("")
    
    parts.append("Context:")
    parts.append(context)
    parts.append("")
    parts.append(f"Question: {question}")
    parts.append("")
    parts.append("Please answer based only on the context above.")
    
    return "\n".join(parts)

