from typing import Optional, Dict, Any
import json

def clean_metadata_for_chunking(
    metadata: Optional[Dict[str, Any]],
    max_metadata_size: int = 500,
) -> Dict[str, Any]:
    """
    Clean metadata to prevent it from exceeding chunk size limits.
    Removes or truncates large fields like coordinates, detection_class_prob, etc.
    
    Args:
        metadata: Original metadata dictionary
        max_metadata_size: Maximum size (in characters) for serialized metadata
        
    Returns:
        Cleaned metadata dictionary
    """
    if not metadata:
        return {}
    
    essential_fields = {
        "page_number", "page_label", "filename", "source_type", 
        "document_id", "chunk_index", "start_time", "end_time",
        "speaker", "segment", "video_id", "source", "source_id", "source_url"
    }
    
    fields_to_remove = {
        "coordinates", "detection_class_prob", "element_id", "type",
        "file_path", "file_hash", "processing_strategy"
    }
    
    cleaned = {}
    for key, value in metadata.items():
        if key in fields_to_remove:
            continue
        
        if key in essential_fields:
            cleaned[key] = value
        elif isinstance(value, (str, int, float, bool)) and len(str(value)) < 100:
            cleaned[key] = value
        elif isinstance(value, (dict, list)):
            try:
                serialized = json.dumps(value)
                if len(serialized) < 100:
                    cleaned[key] = value
            except (TypeError, ValueError):
                pass
    
    try:
        serialized = json.dumps(cleaned)
        if len(serialized) > max_metadata_size:
            essential_only = {k: v for k, v in cleaned.items() if k in essential_fields}
            return essential_only
    except (TypeError, ValueError):
        return {k: v for k, v in cleaned.items() if k in essential_fields}
    
    return cleaned

