"""
Custom node postprocessor that adds source numbering for proper citation.

The problem: LlamaIndex concatenates node texts without numbering, so when we tell
the LLM to "cite using [1], [2]", it has no idea which source corresponds to which number.

The solution: This postprocessor prepends "[Source X]" to each node's text before
it reaches the LLM, enabling accurate inline citations.
"""
from typing import List, Optional
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle
from loguru import logger


class SourceNumberingPostProcessor(BaseNodePostprocessor):
    """
    Postprocessor that adds source numbers to node text for proper citation.
    
    This MUST be the LAST postprocessor in the chain, after reranking and filtering,
    so that the source numbers match the final order of nodes sent to the LLM.
    
    Example:
        Before: "RAFT is a method for fine-tuning LLMs..."
        After:  "[Source 1] RAFT is a method for fine-tuning LLMs..."
    """
    
    include_metadata: bool = True
    
    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        """Add source numbers to each node's text."""
        if not nodes:
            return nodes
        
        numbered_nodes = []
        for i, node_with_score in enumerate(nodes, 1):
            # Clone the node to avoid mutating the original
            node = node_with_score.node.copy()
            
            # Build the source prefix
            prefix_parts = [f"[Source {i}]"]
            
            if self.include_metadata:
                metadata = node.metadata or {}
                filename = metadata.get("filename") or metadata.get("file_name")
                page = metadata.get("page_number")
                
                if filename:
                    prefix_parts.append(f"({filename}")
                    if page is not None:
                        prefix_parts[-1] += f", page {page})"
                    else:
                        prefix_parts[-1] += ")"
            
            # Prepend source number to text
            prefix = " ".join(prefix_parts)
            original_text = node.text or ""
            node.text = f"{prefix}\n{original_text}"
            
            numbered_nodes.append(
                NodeWithScore(node=node, score=node_with_score.score)
            )
        
        logger.debug(f"SourceNumberingPostProcessor: Added source numbers to {len(numbered_nodes)} nodes")
        return numbered_nodes
