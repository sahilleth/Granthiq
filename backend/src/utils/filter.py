from typing import List
from llama_index.core.schema import NodeWithScore   
import hashlib
from loguru import logger
from src.services.ingestion.chunking.chunk_quality import is_junk_chunk
from typing import Dict

def filter_low_quality_results(
    nodes: List[NodeWithScore],
    min_score: float = 0.0001,  
    min_chunk_length: int = 10,  
    min_alpha_ratio: float = 0.1, 
    adaptive: bool = True,  
) -> List[NodeWithScore]:
    """
    Remove ABSOLUTE junk only. Be permissive - let the Reranker decide quality.
    
    IMPORTANT: Qdrant scores are NOT normalized 0-1 probabilities.
    A score of 0.1-0.2 might be excellent depending on the embedding space.
    This function should only filter absolute garbage (empty text, corrupted data).
    
    Args:
        nodes: List of NodeWithScore objects
        min_score: Minimum retrieval score (only filters near-zero/negative)
        min_chunk_length: Minimum chunk length (very low to keep short answers)
        min_alpha_ratio: Minimum ratio of alphabetic characters (relaxed for numeric data)
        adaptive: If True, relaxes thresholds if too many chunks are filtered
    """
    if not nodes:
        return []
    
    filtered = []
    
    for node in nodes:
        # Skip only absolute zero or negative scores (if using cosine)
        if node.score < min_score:
            continue
        
        # Get text from node
        node_text = node.node.text if hasattr(node.node, 'text') else str(node.node)
        if not node_text:
            continue
        
        # Skip only very short chunks (keep short answers like "Status: Active")
        if len(node_text) < min_chunk_length:
            continue
        
        # Skip if it's absolute junk (empty, corrupted, etc.)
        if is_junk_chunk(node_text):
            continue
        
        filtered.append(node)
    
    # Adaptive filtering: if we filtered too many, be even more permissive
    if adaptive and len(filtered) < len(nodes) * 0.3:  # Less than 30% kept
        logger.debug(
            f"Adaptive filtering: {len(filtered)}/{len(nodes)} kept. "
            f"Relaxing thresholds further."
        )
        # Retry with even more relaxed thresholds
        relaxed_filtered = []
        for node in nodes:
            node_text = node.node.text if hasattr(node.node, 'text') else str(node.node)
            if not node_text or not node_text.strip():
                continue
            
            if len(node_text) < 5:  # Absolute minimum
                continue
            
            # Still filter absolute junk
            if is_junk_chunk(node_text):
                continue
            
            relaxed_filtered.append(node)
        
        if len(relaxed_filtered) > len(filtered):
            filtered = relaxed_filtered
            logger.debug(f"Adaptive filtering kept {len(filtered)} chunks (maximum permissiveness)")
    
    if len(nodes) > len(filtered):
        logger.debug(
            f"Filtered {len(nodes) - len(filtered)} absolute junk chunks "
            f"({len(filtered)}/{len(nodes)} kept)"
        )
    
    return filtered

def deduplicate_retrieved_nodes(
    nodes: List[NodeWithScore],
    similarity_threshold: float = 0.95,
) -> List[NodeWithScore]:
    """
    Remove duplicate chunks based on content similarity.
    Keeps the highest-scoring version of duplicate content.
    
    Args:
        nodes: List of NodeWithScore objects
        similarity_threshold: Threshold for considering chunks as duplicates (0-1)
    
    Returns:
        Deduplicated list of NodeWithScore objects
    """
    if not nodes:
        return []
    
    # Use OrderedDict to preserve order while deduplicating
    seen_content: Dict[str, NodeWithScore] = {}
    
    for node in nodes:
        # Get text content
        node_text = node.node.text if hasattr(node.node, 'text') else str(node.node)
        if not node_text:
            continue
        
        # Normalize text for comparison (lowercase, strip whitespace)
        normalized = node_text.lower().strip()
        
        # Create content hash for exact duplicates
        content_hash = hashlib.md5(normalized.encode()).hexdigest()
        
        # Check if we've seen this exact content
        if content_hash in seen_content:
            # Keep the one with higher score
            existing = seen_content[content_hash]
            if node.score > existing.score:
                seen_content[content_hash] = node
        else:
            # Check for near-duplicates (very similar content)
            is_duplicate = False
            for existing_hash, existing_node in list(seen_content.items()):
                existing_text = existing_node.node.text.lower().strip() if hasattr(existing_node.node, 'text') else str(existing_node.node).lower().strip()
                
                # Simple similarity check: if texts are very similar (same length, small differences)
                if abs(len(normalized) - len(existing_text)) / max(len(normalized), len(existing_text), 1) < 0.1:
                    # Check if they're substantially the same (e.g., only whitespace/punctuation differences)
                    if normalized[:100] == existing_text[:100] and len(normalized) > 50:
                        is_duplicate = True
                        # Keep the one with higher score
                        if node.score > existing_node.score:
                            del seen_content[existing_hash]
                            seen_content[content_hash] = node
                        break
            
            if not is_duplicate:
                seen_content[content_hash] = node
    
    deduplicated = list(seen_content.values())
    
    if len(deduplicated) < len(nodes):
        logger.debug(
            f"Deduplicated {len(nodes)} nodes to {len(deduplicated)} "
            f"({len(nodes) - len(deduplicated)} duplicates removed)"
        )
    
    return deduplicated
