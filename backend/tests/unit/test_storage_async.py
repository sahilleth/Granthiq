"""
Unit tests for async storage service.
Tests upload, download, and file operations with async I/O.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path
import tempfile
import io

from src.services.storage import (
    StorageService,
    SignedUrlCache,
    PathTraversalError,
    get_storage_service,
    AIOFILES_AVAILABLE,
)


class TestAsyncFileOperations:
    """Test async file I/O operations in StorageService."""

    @pytest.mark.asyncio
    async def test_upload_local_uses_async_io(self, tmp_path):
        """Test that _upload_local uses async file operations."""
        service = StorageService()
        service.provider = "local"

        # Create test file data
        test_data = b"Test file content"
        test_path = "test/file.txt"
        bucket = "uploads"

        with patch.object(service, '_sanitize_path', return_value="test/file.txt"):
            with patch.object(service, '_validate_path_within_base'):
                with patch('aiofiles.open', AsyncMock()) as mock_aio_open:
                    mock_file = AsyncMock()
                    mock_aio_open.return_value.__aenter__ = AsyncMock(return_value=mock_file)
                    mock_aio_open.return_value.__aexit__ = AsyncMock(return_value=False)

                    if AIOFILES_AVAILABLE:
                        result = await service._upload_local(test_data, test_path, bucket)
                        mock_aio_open.assert_called_once()
                        mock_file.write.assert_called_once_with(test_data)

    @pytest.mark.asyncio
    async def test_download_local_uses_async_io(self, tmp_path):
        """Test that download uses async file operations for local storage."""
        service = StorageService()
        service.provider = "local"

        # Create a test file
        test_dir = tmp_path / "data" / "uploads"
        test_dir.mkdir(parents=True)
        test_file = test_dir / "test.txt"
        test_file.write_bytes(b"Test content")

        with patch('aiofiles.open', AsyncMock()) as mock_aio_open:
            mock_file = AsyncMock()
            mock_file.read = AsyncMock(return_value=b"Test content")
            mock_aio_open.return_value.__aenter__ = AsyncMock(return_value=mock_file)
            mock_aio_open.return_value.__aexit__ = AsyncMock(return_value=False)

            if AIOFILES_AVAILABLE:
                result = await service.download("test.txt", "uploads")
                mock_aio_open.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_stream_local_uses_async_io(self, tmp_path):
        """Test that _upload_stream_local uses async file operations."""
        service = StorageService()
        service.provider = "local"

        # Create a mock file object
        mock_file_obj = io.BytesIO(b"Stream test content")
        test_path = "stream/test.txt"
        bucket = "uploads"

        with patch.object(service, '_sanitize_path', return_value="stream/test.txt"):
            with patch.object(service, '_validate_path_within_base'):
                with patch('aiofiles.open', AsyncMock()) as mock_aio_open:
                    mock_file = AsyncMock()
                    mock_aio_open.return_value.__aenter__ = AsyncMock(return_value=mock_file)
                    mock_aio_open.return_value.__aexit__ = AsyncMock(return_value=False)

                    if AIOFILES_AVAILABLE:
                        result = await service._upload_stream_local(mock_file_obj, test_path, bucket)
                        mock_aio_open.assert_called_once()


class TestStorageServiceAsyncFallback:
    """Test fallback to thread pool when aiofiles is not available."""

    @pytest.mark.asyncio
    async def test_upload_local_fallback_to_thread_pool(self, tmp_path):
        """Test fallback to thread pool when aiofiles unavailable."""
        service = StorageService()
        service.provider = "local"

        test_data = b"Test content"

        with patch('src.services.storage.AIOFILES_AVAILABLE', False):
            with patch.object(service, '_sanitize_path', return_value="test.txt"):
                with patch.object(service, '_validate_path_within_base'):
                    with patch('asyncio.to_thread', AsyncMock()) as mock_to_thread:
                        mock_to_thread.return_value = None

                        await service._upload_local(test_data, "test.txt", "uploads")
                        mock_to_thread.assert_called_once()


class TestPathTraversalProtection:
    """Test path traversal protection in storage service."""

    def test_sanitize_path_removes_traversal(self):
        """Test that _sanitize_path blocks path traversal attempts."""
        service = StorageService()

        # Test various traversal attempts
        with pytest.raises(PathTraversalError):
            service._sanitize_path("../../../etc/passwd")

        with pytest.raises(PathTraversalError):
            service._sanitize_path("..\\..\\windows\\system32\\config\\sam")

    def test_sanitize_path_allows_valid_paths(self):
        """Test that _sanitize_path allows valid paths."""
        service = StorageService()

        valid_paths = [
            "documents/file.pdf",
            "uploads/images/photo.jpg",
            "file.txt",
        ]

        for path in valid_paths:
            result = service._sanitize_path(path)
            assert result == path

    def test_validate_path_within_base_blocks_escape(self):
        """Test that _validate_path_within_base blocks directory escape."""
        service = StorageService()

        base_dir = Path("/data/uploads")
        # Path that escapes base directory
        malicious_path = Path("/data/uploads/../../etc/passwd")

        with pytest.raises(PathTraversalError):
            service._validate_path_within_base(malicious_path, base_dir)


class TestSignedUrlCache:
    """Test SignedUrlCache functionality."""

    def test_cache_get_existing(self):
        """Test getting a cached URL that exists and hasn't expired."""
        cache = SignedUrlCache(default_ttl_seconds=300)
        cache.set("test-key", "https://example.com/signed-url")

        result = cache.get("test-key")

        assert result == "https://example.com/signed-url"

    def test_cache_get_missing(self):
        """Test getting a cached URL that doesn't exist."""
        cache = SignedUrlCache()

        result = cache.get("nonexistent-key")

        assert result is None

    def test_cache_get_expired(self):
        """Test getting a cached URL that has expired."""
        import time
        cache = SignedUrlCache(default_ttl_seconds=0)  # Immediate expiration
        cache.set("expired-key", "https://example.com/signed-url")

        # Wait a tiny bit for expiration
        time.sleep(0.01)

        result = cache.get("expired-key")

        assert result is None

    def test_cache_cleanup_expired(self):
        """Test cleanup of expired entries."""
        import time
        cache = SignedUrlCache(default_ttl_seconds=0)
        cache.set("key1", "url1")
        cache.set("key2", "url2")

        time.sleep(0.01)

        removed = cache.cleanup_expired()

        assert removed == 2
        assert cache.get("key1") is None
        assert cache.get("key2") is None


class TestStorageServiceProviderSelection:
    """Test storage provider selection and configuration."""

    def test_get_storage_service_returns_instance(self):
        """Test that get_storage_service returns a StorageService instance."""
        service = get_storage_service()
        assert isinstance(service, StorageService)

    def test_storage_service_initializes_with_settings(self):
        """Test that StorageService initializes with settings."""
        with patch('src.services.storage.get_settings') as mock_get_settings:
            mock_settings = Mock()
            mock_settings.storage.provider = "local"
            mock_settings.storage.supabase_url = None
            mock_settings.storage.supabase_key = None
            mock_get_settings.return_value = mock_settings

            service = StorageService()
            assert service.provider == "local"
