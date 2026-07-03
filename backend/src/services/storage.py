import os
import re
import time
from pathlib import Path
from typing import Optional, Dict, Tuple
from loguru import logger
from supabase import create_client, Client

# Use aiofiles for async file operations
try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False
    logger.warning("aiofiles not installed. Using synchronous file operations in async context.")

from src.config import get_settings
from src.utils.retry import retry_on_storage_error


# Cache entry type: (url, expiration_timestamp)
SignedUrlCacheEntry = Tuple[str, float]


class SignedUrlCache:
    """
    Simple in-memory cache for signed URLs with TTL support.
    
    URLs expire in 1 hour from Supabase, so we cache them for 50 minutes
    to ensure we don't return expired URLs.
    """
    
    def __init__(self, default_ttl_seconds: int = 3000):  # 50 minutes default
        self._cache: Dict[str, SignedUrlCacheEntry] = {}
        self._default_ttl = default_ttl_seconds
    
    def get(self, key: str) -> Optional[str]:
        """Get a cached URL if it hasn't expired."""
        if key not in self._cache:
            return None
        
        url, expiration = self._cache[key]
        if time.time() > expiration:
            # URL has expired, remove from cache
            del self._cache[key]
            return None
        
        return url
    
    def set(self, key: str, url: str, ttl_seconds: Optional[int] = None) -> None:
        """Cache a URL with expiration time."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expiration = time.time() + ttl
        self._cache[key] = (url, expiration)
        logger.debug(f"Cached signed URL for key: {key}, expires in {ttl}s")
    
    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.debug("Signed URL cache cleared")
    
    def cleanup_expired(self) -> int:
        """Remove expired entries and return count of removed entries."""
        now = time.time()
        expired_keys = [k for k, (_, exp) in self._cache.items() if now > exp]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)


class PathTraversalError(ValueError):
    """Raised when path traversal attempt is detected."""
    pass


class StorageService:
    """
    Abstracts file storage operations (Local vs Supabase).
    Handles Public vs Private buckets seamlessly.
    Includes path traversal protection and signed URL caching.
    """

    # Characters not allowed in safe filenames
    UNSAFE_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')

    # Maximum path depth to prevent deeply nested attacks
    MAX_PATH_DEPTH = 10
    
    # Signed URL cache TTL (50 minutes - URLs expire in 1 hour from Supabase)
    SIGNED_URL_CACHE_TTL = 3000  # 50 minutes in seconds

    def __init__(self):
        self.settings = get_settings()
        self.provider = self.settings.storage.provider
        self.client: Optional[Client] = None
        self._signed_url_cache = SignedUrlCache(default_ttl_seconds=self.SIGNED_URL_CACHE_TTL)
        
        if self.provider == "supabase":
            if not self.settings.storage.supabase_url or not self.settings.storage.supabase_key:
                logger.error("Supabase credentials missing in settings.")
            else:
                try:
                    # Ensure URL has trailing slash to avoid Supabase client warning
                    supabase_url = self.settings.storage.supabase_url
                    if supabase_url and not supabase_url.endswith('/'):
                        supabase_url = supabase_url + '/'
                    
                    self.client = create_client(
                        supabase_url, 
                        self.settings.storage.supabase_key
                    )
                except Exception as e:
                    logger.error(f"Failed to initialize Supabase client: {e}")

    async def upload(
        self, 
        file_data: bytes, 
        path: str, 
        bucket: str, 
        mime_type: str = "application/octet-stream"
    ) -> str:
        """
        Uploads file to storage.
        Returns the path/key (not the full URL).
        
        DEPRECATED: Use upload_stream for production to avoid loading entire file into RAM.
        """
        if self.provider == "local":
            return await self._upload_local(file_data, path, bucket)
        
        if self.provider == "supabase" and self.client:
            return await self._upload_supabase(file_data, path, bucket, mime_type)
            
        raise ValueError(f"Invalid storage provider configuration: {self.provider}")
    
    async def ensure_bucket_exists(self, bucket: str, is_public: bool = False):
        """
        Ensure a bucket exists, create it if it doesn't.
        
        Args:
            bucket: Bucket name
            is_public: Whether the bucket should be public
            
        Raises:
            ValueError: If bucket doesn't exist and cannot be created automatically
        """
        if self.provider == "local":
            # For local storage, just ensure directory exists
            base_dir = Path("data") / bucket
            base_dir.mkdir(parents=True, exist_ok=True)
            return
        
        if self.provider == "supabase" and self.client:
            try:
                # Try to list buckets to check existence
                try:
                    buckets_response = self.client.storage.list_buckets()
                    
                    # Handle response - can be response object with .data or direct list
                    buckets = []
                    if hasattr(buckets_response, 'data'):
                        buckets = buckets_response.data if buckets_response.data else []
                    elif isinstance(buckets_response, list):
                        buckets = buckets_response
                    else:
                        buckets = list(buckets_response) if hasattr(buckets_response, '__iter__') else []
                    
                    # Extract bucket names
                    bucket_names = []
                    for b in buckets:
                        if hasattr(b, 'name'):
                            bucket_names.append(b.name)
                        elif isinstance(b, dict):
                            bucket_names.append(b.get('name', ''))
                        else:
                            bucket_names.append(str(b))
                    
                    if bucket not in bucket_names:
                        logger.warning(f"Bucket '{bucket}' does not exist. Attempting to create it...")
                        try:
                            # According to Supabase docs: create_bucket(name, options={})
                            # Options: public, allowed_mime_types, file_size_limit
                            response = self.client.storage.create_bucket(
                                bucket,
                                options={
                                    "public": is_public,
                                    "allowed_mime_types": None,  # Allow all file types
                                    "file_size_limit": None,  # No size limit
                                }
                            )
                            logger.success(f"Bucket '{bucket}' created successfully (public={is_public})")
                        except Exception as create_error:
                            logger.error(f"Failed to create bucket '{bucket}' automatically: {create_error}")
                            logger.error(f"Please create the bucket manually in Supabase Storage dashboard:")
                            # Construct proper dashboard URL
                            dashboard_url = self.settings.storage.supabase_url
                            if dashboard_url and 'supabase' in dashboard_url:
                                # Extract project ref if possible
                                if '.supabase.co' in dashboard_url:
                                    project_ref = dashboard_url.split('//')[1].split('.')[0] if '//' in dashboard_url else None
                                    if project_ref:
                                        dashboard_url = f"https://app.supabase.com/project/{project_ref}/storage/buckets"
                                else:
                                    dashboard_url = f"{dashboard_url}/storage/buckets"
                            else:
                                dashboard_url = "Supabase Dashboard > Storage > Buckets"
                            
                            logger.error(f"   1. Go to: {dashboard_url}")
                            logger.error(f"   2. Click '+ New bucket'")
                            logger.error(f"   3. Name: '{bucket}'")
                            logger.error(f"   4. Public: {is_public}")
                            raise ValueError(
                                f"Storage bucket '{bucket}' does not exist and could not be created automatically. "
                                f"Please create it manually in the Supabase Storage dashboard. "
                                f"Error: {create_error}"
                            )
                    else:
                        logger.debug(f"Bucket '{bucket}' exists")
                except Exception as list_error:
                    # If we can't list buckets, log a warning but don't fail
                    logger.warning(f"Could not verify bucket existence: {list_error}. Proceeding with upload...")
            except ValueError:
                # Re-raise ValueError from bucket creation failure
                raise
            except Exception as e:
                logger.error(f"Unexpected error checking bucket '{bucket}': {e}")
                # Don't fail if we can't check - let the upload attempt happen and fail with a clearer error

    def _sanitize_path(self, path: str) -> str:
        """
        Sanitize a path to prevent path traversal attacks.

        Security measures:
        - Removes null bytes
        - Strips path traversal sequences (../)
        - Removes leading slashes
        - Validates against unsafe characters
        - Limits path depth

        Args:
            path: User-provided path

        Returns:
            Sanitized path

        Raises:
            PathTraversalError: If path traversal is detected
        """
        if not path:
            raise ValueError("Path cannot be empty")

        # Remove null bytes
        path = path.replace('\x00', '')

        # Check for unsafe characters
        if self.UNSAFE_CHARS.search(path):
            unsafe_found = self.UNSAFE_CHARS.findall(path)
            raise PathTraversalError(f"Path contains unsafe characters: {unsafe_found}")

        # Normalize path and check for traversal attempts
        path_obj = Path(path)

        # Count path components (depth check)
        parts = path_obj.parts
        if len(parts) > self.MAX_PATH_DEPTH:
            raise PathTraversalError(f"Path too deep: {len(parts)} components (max {self.MAX_PATH_DEPTH})")

        # Check for traversal attempts in parts
        traversal_attempts = [p for p in parts if p == '..' or p.startswith('../')]
        if traversal_attempts:
            raise PathTraversalError(f"Path traversal detected: {traversal_attempts}")

        # Remove leading slashes and normalize
        safe_path = path.lstrip('/').lstrip('\\')

        # Additional check: ensure no absolute path
        if Path(safe_path).is_absolute():
            raise PathTraversalError("Absolute paths are not allowed")

        return safe_path

    def _validate_path_within_base(self, full_path: Path, base_dir: Path) -> None:
        """
        Validate that full_path is within base_dir after resolution.

        This is the critical security check that prevents path traversal.

        Args:
            full_path: The resolved full path
            base_dir: The allowed base directory

        Raises:
            PathTraversalError: If path escapes base directory
        """
        try:
            # Resolve to absolute paths (follows symlinks)
            full_resolved = full_path.resolve()
            base_resolved = base_dir.resolve()

            # Check if full_path is within base_dir
            # Use relative_to which raises ValueError if not a subpath
            full_resolved.relative_to(base_resolved)

        except (ValueError, RuntimeError) as e:
            logger.error(
                f"Path traversal attempt blocked: {full_path} is outside {base_dir}"
            )
            raise PathTraversalError(
                f"Access denied: path escapes allowed directory"
            ) from e

    async def upload_stream(
        self,
        file_obj,
        path: str,
        bucket: str,
        mime_type: str = "application/octet-stream"
    ) -> str:
        """
        Uploads file from a file-like object (streaming upload).
        This avoids loading the entire file into RAM.
        
        Args:
            file_obj: File-like object (e.g., SpooledTemporaryFile from UploadFile)
            path: Storage path/key
            bucket: Bucket name
            mime_type: MIME type
            
        Returns:
            The path/key (not the full URL)
        """
        # Ensure bucket exists before upload
        if self.provider == "supabase":
            # Determine if bucket should be public based on bucket name
            is_public = "public" in bucket.lower()
            await self.ensure_bucket_exists(bucket, is_public=is_public)
        
        if self.provider == "local":
            return await self._upload_stream_local(file_obj, path, bucket)
        
        if self.provider == "supabase" and self.client:
            return await self._upload_stream_supabase(file_obj, path, bucket, mime_type)
            
        raise ValueError(f"Invalid storage provider configuration: {self.provider}")

    async def _upload_local(self, file_data: bytes, path: str, bucket: str) -> str:
        """
        Upload file to local storage with path traversal protection.
        Uses aiofiles for async file operations when available.
        """
        # Sanitize the path
        safe_path = self._sanitize_path(path)

        # Build paths
        base_dir = Path("data") / bucket
        full_path = base_dir / safe_path

        # Critical security check: ensure path is within base_dir
        self._validate_path_within_base(full_path, base_dir)

        # Create directories (sync is acceptable for directory creation)
        base_dir.mkdir(parents=True, exist_ok=True)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file using aiofiles if available, otherwise use sync in thread
        if AIOFILES_AVAILABLE:
            async with aiofiles.open(full_path, "wb") as f:
                await f.write(file_data)
        else:
            # Fallback: run sync file operation in thread pool
            import asyncio
            await asyncio.to_thread(self._write_file_sync, full_path, file_data)

        logger.debug(f"Uploaded to local storage: {full_path}")
        return safe_path

    def _write_file_sync(self, full_path: Path, file_data: bytes) -> None:
        """Synchronous file write helper for thread pool fallback."""
        with open(full_path, "wb") as f:
            f.write(file_data)

    async def _upload_stream_local(self, file_obj, path: str, bucket: str) -> str:
        """
        Stream upload for local storage with path traversal protection.
        Uses aiofiles for async file operations when available.
        """
        # Sanitize the path
        safe_path = self._sanitize_path(path)

        # Build paths
        base_dir = Path("data") / bucket
        full_path = base_dir / safe_path

        # Critical security check
        self._validate_path_within_base(full_path, base_dir)

        # Create directories (sync is acceptable for directory creation)
        base_dir.mkdir(parents=True, exist_ok=True)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Stream write using aiofiles if available
        file_obj.seek(0)
        if AIOFILES_AVAILABLE:
            async with aiofiles.open(full_path, "wb") as f:
                chunk_size = 8192
                while True:
                    chunk = file_obj.read(chunk_size)
                    if not chunk:
                        break
                    await f.write(chunk)
        else:
            # Fallback: run sync file operation in thread pool
            import asyncio
            await asyncio.to_thread(self._write_stream_sync, full_path, file_obj)

        return safe_path

    def _write_stream_sync(self, full_path: Path, file_obj) -> None:
        """Synchronous stream write helper for thread pool fallback."""
        file_obj.seek(0)
        with open(full_path, "wb") as f:
            chunk_size = 8192
            while True:
                chunk = file_obj.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)

    @retry_on_storage_error(max_attempts=3)
    async def _upload_supabase(self, file_data: bytes, path: str, bucket: str, mime_type: str) -> str:
        try:
            # Sync call wrapper (Supabase python client is synchronous for storage currently)
            # Upsert=True allows overwriting
            res = self.client.storage.from_(bucket).upload(
                path=path,
                file=file_data,
                file_options={"content-type": mime_type, "upsert": "true"}
            )
            logger.info(f"Uploaded to Supabase: {path} (Bucket: {bucket})")
            return path
        except Exception as e:
            logger.error(f"Supabase Upload Failed: {e}")
            raise e
    
    @retry_on_storage_error(max_attempts=3)
    async def _upload_stream_supabase(self, file_obj, path: str, bucket: str, mime_type: str) -> str:
        """Stream upload for Supabase storage with retry logic."""
        try:
            # Seek to start in case file was already read
            file_obj.seek(0)
            
            # Validate file size for Supabase (50MB limit on free tier)
            # Get file size by seeking to end
            file_obj.seek(0, 2)  # Seek to end
            file_size = file_obj.tell()
            file_obj.seek(0)  # Reset to start
            
            max_size_bytes = self.settings.storage.max_file_size_mb * 1024 * 1024
            if file_size > max_size_bytes:
                file_size_mb = file_size / (1024 * 1024)
                raise ValueError(
                    f"File size ({file_size_mb:.2f} MB) exceeds Supabase free tier limit "
                    f"({self.settings.storage.max_file_size_mb} MB per file). "
                    f"For larger files, consider migrating to Cloudflare R2 or Backblaze B2. "
                    f"See docs/STORAGE_RECOMMENDATIONS.md for setup instructions."
                )
            
            # Supabase Python client's upload method requires bytes, not file-like objects
            # Read the file content into bytes
            file_data = file_obj.read()
            
            # Upload bytes to Supabase
            res = self.client.storage.from_(bucket).upload(
                path=path,
                file=file_data,  # Pass bytes directly
                file_options={"content-type": mime_type, "upsert": "true"}
            )
            logger.info(f"Uploaded to Supabase: {path} (Bucket: {bucket}, Size: {file_size / (1024*1024):.2f} MB)")
            return path
        except ValueError as e:
            # Re-raise file size errors with clear message
            logger.error(f"File size validation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Supabase Stream Upload Failed: {e}")
            raise e

    async def get_url(self, path: str, bucket: str, private: bool = False) -> str:
        """
        Generates a URL for the file.
        - private=True: Generates a signed URL (valid for 1 hour).
        - private=False: Generates a public URL.
        """
        if self.provider == "local":
            # Just return a placeholder for local dev if not using a static file server
            return f"http://localhost:8000/static/{bucket}/{path}"

        if self.provider == "supabase" and self.client:
            # Ensure bucket exists before generating URL
            is_public = not private  # Private buckets are not public by default
            await self.ensure_bucket_exists(bucket, is_public=is_public)
            
            try:
                if private:
                    # Check cache first for signed URLs
                    cache_key = f"{bucket}:{path}"
                    cached_url = self._signed_url_cache.get(cache_key)
                    if cached_url:
                        logger.debug(f"Using cached signed URL for {path}")
                        return cached_url
                    
                    # Generate new signed URL (valid for 1 hour from Supabase)
                    response = self.client.storage.from_(bucket).create_signed_url(path, 3600)
                    if isinstance(response, dict) and 'signedURL' in response:
                        signed_url = response['signedURL']
                        # Cache the signed URL
                        self._signed_url_cache.set(cache_key, signed_url)
                        return signed_url
                    return response # Fallback if string
                else:
                    # Public URL - no caching needed as they don't expire
                    return self.client.storage.from_(bucket).get_public_url(path)
            except Exception as e:
                logger.error(f"Failed to generate URL for {path} in bucket {bucket}: {e}")
                logger.error(f"Make sure the bucket '{bucket}' exists in your Supabase Storage dashboard")
                return ""
        
        return ""

    async def download(self, path: str, bucket: str) -> bytes:
        """
        Download file from storage and return bytes.

        Args:
            path: Storage path/key
            bucket: Bucket name

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If storage provider is invalid
        """
        if self.provider == "local":
            full_path = Path("data") / bucket / path
            if not full_path.exists():
                raise FileNotFoundError(f"File not found: {full_path}")

            # Use aiofiles if available, otherwise thread pool
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(full_path, "rb") as f:
                    return await f.read()
            else:
                import asyncio
                return await asyncio.to_thread(self._read_file_sync, full_path)

        if self.provider == "supabase" and self.client:
            try:
                # Supabase storage download returns bytes
                response = self.client.storage.from_(bucket).download(path)
                logger.info(f"Downloaded from Supabase: {path} (Bucket: {bucket})")
                return response
            except Exception as e:
                logger.error(f"Supabase Download Failed for {path}: {e}")
                raise FileNotFoundError(f"Failed to download {path} from {bucket}: {e}")

        raise ValueError(f"Invalid storage provider configuration: {self.provider}")

    def _read_file_sync(self, full_path: Path) -> bytes:
        """Synchronous file read helper for thread pool fallback."""
        with open(full_path, "rb") as f:
            return f.read()

    async def download_to_temp(self, path: str, bucket: str, temp_dir: Optional[Path] = None) -> Path:
        """
        Download file from storage to a temporary file.

        Args:
            path: Storage path/key
            bucket: Bucket name
            temp_dir: Optional temp directory (uses system temp if not provided)

        Returns:
            Path to the downloaded temporary file

        Note:
            Caller is responsible for cleaning up the temp file.
        """
        import tempfile
        import asyncio

        # Download file bytes
        file_data = await self.download(path, bucket)

        # Determine file extension from path
        file_ext = Path(path).suffix or ""

        # Create temp directory if provided, otherwise use system temp
        if temp_dir:
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file_path = temp_dir / f"download_{os.urandom(8).hex()}{file_ext}"

            # Use aiofiles if available, otherwise thread pool
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(temp_file_path, "wb") as f:
                    await f.write(file_data)
            else:
                await asyncio.to_thread(self._write_file_sync, temp_file_path, file_data)
        else:
            # Use tempfile module for system temp directory
            # tempfile operations are inherently sync, but we minimize blocking time
            def create_temp_file():
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as f:
                    f.write(file_data)
                    return Path(f.name)

            temp_file_path = await asyncio.to_thread(create_temp_file)

        logger.info(f"Downloaded to temp file: {temp_file_path}")
        return temp_file_path

    def delete(self, path: str, bucket: str):
        """Delete file from storage."""
        if self.provider == "local":
            full_path = Path("data") / bucket / path
            if full_path.exists():
                os.remove(full_path)
            return

        if self.provider == "supabase" and self.client:
            try:
                self.client.storage.from_(bucket).remove([path])
            except Exception as e:
                logger.error(f"Supabase Delete Failed: {e}")

def get_storage_service() -> StorageService:
    """Dependency to get storage service instance."""
    return StorageService()