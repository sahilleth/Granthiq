"""
Security utilities for the application.
"""

import os
import re
import uuid


def sanitize_filename(filename: str) -> str:
    r"""
    Sanitize filename to prevent path traversal attacks and special characters.
    
    Security measures:
    - Remove path separators (/, \)
    - Remove parent directory references (..)
    - Remove special characters except word chars, spaces, dots, dashes, underscores
    - Limit length to 255 characters
    - Preserve file extension
    
    Args:
        filename: Original filename from user upload
        
    Returns:
        Safe filename suitable for storage
        
    Examples:
        >>> sanitize_filename("../../etc/passwd")
        'etcpasswd'
        >>> sanitize_filename("file<>name?.txt")
        'filename.txt'
        >>> sanitize_filename("normal_file-2024.pdf")
        'normal_file-2024.pdf'
    """
    # Remove any path components
    filename = os.path.basename(filename)
    
    # Remove parent directory references
    filename = filename.replace('..', '')
    
    # Split extension to preserve it
    name_parts = filename.rsplit('.', 1)
    name = name_parts[0]
    ext = '.' + name_parts[1] if len(name_parts) > 1 else ''
    
    # Remove special characters (keep word chars, spaces, dots, dashes, underscores)
    safe_name = re.sub(r'[^\w\s.-]', '', name)
    safe_name = safe_name.strip()
    
    # Rebuild with safe extension
    safe_ext = re.sub(r'[^\w.-]', '', ext)
    safe_filename = safe_name + safe_ext
    
    # Limit total length (filesystem limit)
    if len(safe_filename) > 255:
        # Preserve extension, truncate name
        max_name_len = 255 - len(safe_ext)
        safe_filename = safe_name[:max_name_len] + safe_ext
    
    # Fallback if empty after sanitization
    if not safe_filename or safe_filename == safe_ext:
        safe_filename = f"document_{uuid.uuid4().hex[:8]}{safe_ext}"
    
    return safe_filename
