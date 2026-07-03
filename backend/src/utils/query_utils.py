from llama_index.core.response_synthesizers import ResponseMode
from loguru import logger

def _map_response_mode(mode_str: str) -> ResponseMode:
    """
    Map config string to LlamaIndex ResponseMode enum.
    
    Args:
        mode_str: Response mode string from config
        
    Returns:
        ResponseMode enum value
    """
    mapping = {
        "compact": ResponseMode.COMPACT,
        "compact_accumulate": ResponseMode.COMPACT_ACCUMULATE,
        "refine": ResponseMode.REFINE,
        "simple_summarize": ResponseMode.SIMPLE_SUMMARIZE,
        "tree_summarize": ResponseMode.TREE_SUMMARIZE,
    }
    
    mode_lower = mode_str.lower().strip()
    if mode_lower in mapping:
        return mapping[mode_lower]
    
    logger.warning(
        f"Unknown response_mode '{mode_str}', defaulting to COMPACT. "
        f"Valid options: {list(mapping.keys())}"
    )
    return ResponseMode.COMPACT