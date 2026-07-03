import hashlib
import mimetypes
from pathlib import Path
from typing import Optional, List

from loguru import logger

from src.utils.exceptions import FileSizeError, FileTypeError, FileValidationError



SUPPORTED_DOCUMENT_TYPES = {
    '.pdf': 'application/pdf',
    '.txt': 'text/plain',
    '.md': 'text/markdown',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.doc': 'application/msword',
}

SUPPORTED_AUDIO_TYPES = {
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.m4a': 'audio/mp4',
    '.ogg': 'audio/ogg',
    '.flac': 'audio/flac',
}

ALL_SUPPORTED_TYPES = {**SUPPORTED_DOCUMENT_TYPES, **SUPPORTED_AUDIO_TYPES}


def validate_file_size(
    file_path: Path | str,
    max_size_mb: int = 50
) -> None:
    """
    Validate that a file doesn't exceed the maximum size.
    
    Args:
        file_path: Path to the file
        max_size_mb: Maximum allowed size in megabytes
        
    Raises:
        FileSizeError: If file exceeds maximum size
        FileValidationError: If file doesn't exist
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileValidationError(f"File does not exist: {file_path}")
    
    file_size_bytes = file_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    
    if file_size_mb > max_size_mb:
        raise FileSizeError(
            f"File size ({file_size_mb:.2f} MB) exceeds maximum allowed size ({max_size_mb} MB)"
        )
    
    logger.debug(f"File size validation passed: {file_path.name} ({file_size_mb:.2f} MB)")


def validate_file_type(
    file_path: Path | str,
    allowed_extensions: Optional[List[str]] = None
) -> str:
    """
    Validate file type and return the file extension.
    
    Args:
        file_path: Path to the file
        allowed_extensions: List of allowed extensions (e.g., ['.pdf', '.txt'])
                          If None, uses ALL_SUPPORTED_TYPES
        
    Returns:
        The file extension (lowercase)
        
    Raises:
        FileTypeError: If file type is not supported
    """
    file_path = Path(file_path)
    extension = file_path.suffix.lower()
    
    if allowed_extensions is None:
        allowed_extensions = list(ALL_SUPPORTED_TYPES.keys())
    
    if extension not in allowed_extensions:
        raise FileTypeError(
            f"Unsupported file type: {extension}. "
            f"Supported types: {', '.join(allowed_extensions)}"
        )
    
    logger.debug(f"File type validation passed: {file_path.name} ({extension})")
    return extension


def get_file_hash(
    file_path: Path | str,
    algorithm: str = 'sha256'
) -> str:
    """
    Calculate the hash of a file for deduplication and integrity checking.
    
    Args:
        file_path: Path to the file
        algorithm: Hash algorithm to use ('md5', 'sha1', 'sha256', etc.)
        
    Returns:
        Hexadecimal hash string
        
    Raises:
        FileValidationError: If file doesn't exist or can't be read
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileValidationError(f"File does not exist: {file_path}")
    
    try:
        hash_func = hashlib.new(algorithm)
        
      
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_func.update(chunk)
        
        file_hash = hash_func.hexdigest()
        logger.debug(f"Generated {algorithm} hash for {file_path.name}: {file_hash[:16]}...")
        
        return file_hash
        
    except Exception as e:
        raise FileValidationError(f"Error calculating file hash: {str(e)}") from e


def get_file_mime_type(file_path: Path | str) -> Optional[str]:
    """
    Get the MIME type of a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        MIME type string or None if unknown
    """
    file_path = Path(file_path)
    extension = file_path.suffix.lower()
    
   
    if extension in ALL_SUPPORTED_TYPES:
        return ALL_SUPPORTED_TYPES[extension]
    
   
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize a filename by removing invalid characters.
    
    Args:
        filename: Original filename
        max_length: Maximum filename length
        
    Returns:
        Sanitized filename
    """
    import re
    
   
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    
   
    filename = filename.strip(' .')
    
   
    if not filename:
        filename = 'unnamed_file'
    
   
    if len(filename) > max_length:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        max_name_length = max_length - len(ext) - 1 if ext else max_length
        filename = f"{name[:max_name_length]}.{ext}" if ext else name[:max_length]
    
    return filename


def ensure_directory(directory: Path | str) -> Path:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        directory: Path to the directory
        
    Returns:
        Path object for the directory
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_file_size_mb(file_path: Path | str) -> float:
    """
    Get file size in megabytes.
    
    Args:
        file_path: Path to the file
        
    Returns:
        File size in MB
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return 0.0
    
    return file_path.stat().st_size / (1024 * 1024)


def is_document_file(file_path: Path | str) -> bool:
    """
    Check if a file is a supported document type.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file is a supported document type
    """
    file_path = Path(file_path)
    return file_path.suffix.lower() in SUPPORTED_DOCUMENT_TYPES


def is_audio_file(file_path: Path | str) -> bool:
    """
    Check if a file is a supported audio type.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file is a supported audio type
    """
    file_path = Path(file_path)
    return file_path.suffix.lower() in SUPPORTED_AUDIO_TYPES


def get_safe_path(base_dir: Path | str, filename: str) -> Path:
    """
    Get a safe file path, preventing directory traversal attacks.
    
    Args:
        base_dir: Base directory
        filename: Requested filename
        
    Returns:
        Safe path within the base directory
        
    Raises:
        FileValidationError: If path would escape base directory
    """
    base_dir = Path(base_dir).resolve()
    file_path = (base_dir / filename).resolve()
    
   
    try:
        file_path.relative_to(base_dir)
    except ValueError:
        raise FileValidationError(
            f"Invalid path: {filename} would escape base directory"
        )
    
    return file_path


def get_unique_filename(directory: Path | str, filename: str) -> Path:
    """
    Get a unique filename in a directory by adding a number if needed.
    
    Args:
        directory: Target directory
        filename: Desired filename
        
    Returns:
        Path with unique filename
    """
    directory = Path(directory)
    file_path = directory / filename
    
    if not file_path.exists():
        return file_path
    
   
    name = file_path.stem
    extension = file_path.suffix
    
   
    counter = 1
    while True:
        new_path = directory / f"{name}_{counter}{extension}"
        if not new_path.exists():
            return new_path
        counter += 1

