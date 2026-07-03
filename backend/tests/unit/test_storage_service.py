"""
Unit tests for StorageService.
Tests upload, download, signed URL generation, and caching.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path
import tempfile
import time

from src.services.storage import (
    StorageService, 
    SignedUrlCache, 
    PathTraversalError,
    get_storage_service
)


class TestSignedUrlCache:
    """Test SignedUrlCache class."""

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
        cache = SignedUrlCache(default_ttl_seconds=0)  # Immediate expiration
        cache.set("expired-key", "https://example.com/signed-url")
        
        # Wait a tiny bit for expiration
        time.sleep(0.01)
        
        result = cache.get("expired-key")
        
        assert result is None
        assert "expired-key" not in cache._cache

    def test_cache_set_with_custom_ttl(self):
        """Test setting a cache entry with custom TTL."""
        cache = SignedUrlCache()
        cache.set("key", "url", ttl_seconds=600)
        
        entry = cache._cache["key"]
        assert entry[0] == "url"
        # Check expiration is roughly 600 seconds from now
        assert entry[1] > time.time() + 590

    def test_cache_clear(self):
        """Test clearing all cache entries."""
        cache = SignedUrlCache()
        cache.set("key1", "url1")
        cache.set("key2", "url2")
        
        cache.clear()
        
        assert len(cache._cache) == 0

    def test_cache_cleanup_expired(self):
        """Test cleaning up expired entries."""
        cache = SignedUrlCache()
        
        # Add one expired entry
        cache._cache["expired"] = ("url", time.time() - 1)
        # Add one valid entry
        cache.set("valid", "url")
        
        removed = cache.cleanup_expired()
        
        assert removed == 1
        assert "expired" not in cache._cache
        assert "valid" in cache._cache


class TestStorageServiceInitialization:
    """Test StorageService initialization."""

    @patch('src.services.storage.get_settings')
    def test_init_local_provider(self, mock_get_settings):
        """Test initialization with local provider."""
        settings = Mock()
        settings.storage.provider = "local"
        mock_get_settings.return_value = settings
        
        service = StorageService()
        
        assert service.provider == "local"
        assert service.client is None

    @patch('src.services.storage.get_settings')
    def test_init_supabase_no_credentials(self, mock_get_settings):
        """Test initialization with Supabase but no credentials."""
        settings = Mock()
        settings.storage.provider = "supabase"
        settings.storage.supabase_url = None
        settings.storage.supabase_key = None
        mock_get_settings.return_value = settings
        
        service = StorageService()
        
        assert service.provider == "supabase"
        assert service.client is None

    @patch('src.services.storage.get_settings')
    @patch('src.services.storage.create_client')
    def test_init_supabase_with_credentials(self, mock_create_client, mock_get_settings):
        """Test initialization with Supabase credentials."""
        settings = Mock()
        settings.storage.provider = "supabase"
        settings.storage.supabase_url = "https://test.supabase.co"
        settings.storage.supabase_key = "test-key"
        mock_get_settings.return_value = settings
        mock_create_client.return_value = Mock()
        
        service = StorageService()
        
        assert service.provider == "supabase"
        assert service.client is not None


class TestStorageServicePathSanitization:
    """Test path sanitization methods."""

    @pytest.fixture
    def service(self):
        with patch('src.services.storage.get_settings') as mock_get_settings:
            settings = Mock()
            settings.storage.provider = "local"
            mock_get_settings.return_value = settings
            return StorageService()

    def test_sanitize_path_valid(self, service):
        """Test sanitizing a valid path."""
        result = service._sanitize_path("documents/test.pdf")
        
        assert result == "documents/test.pdf"

    def test_sanitize_path_with_leading_slash(self, service):
        """Test sanitizing path with leading slash."""
        result = service._sanitize_path("/documents/test.pdf")
        
        assert result == "documents/test.pdf"

    def test_sanitize_path_empty(self, service):
        """Test sanitizing empty path raises error."""
        with pytest.raises(ValueError, match="Path cannot be empty"):
            service._sanitize_path("")

    def test_sanitize_path_traversal_attempt(self, service):
        """Test sanitizing path with traversal attempt."""
        with pytest.raises(PathTraversalError):
            service._sanitize_path("../etc/passwd")

    def test_sanitize_path_unsafe_characters(self, service):
        """Test sanitizing path with unsafe characters."""
        with pytest.raises(PathTraversalError):
            service._sanitize_path("file<name>.pdf")

    def test_sanitize_path_too_deep(self, service):
        """Test sanitizing path that exceeds max depth."""
        deep_path = "/".join(["dir"] * 15)
        with pytest.raises(PathTraversalError):
            service._sanitize_path(deep_path)

    def test_validate_path_within_base_valid(self, service):
        """Test validating path within base directory."""
        base_dir = Path("/data/uploads")
        full_path = Path("/data/uploads/documents/test.pdf")
        
        # Should not raise
        service._validate_path_within_base(full_path, base_dir)

    def test_validate_path_within_base_invalid(self, service):
        """Test validating path outside base directory."""
        base_dir = Path("/data/uploads")
        full_path = Path("/etc/passwd")
        
        with pytest.raises(PathTraversalError):
            service._validate_path_within_base(full_path, base_dir)


class TestStorageServiceUpload:
    """Test upload operations."""

    @pytest.fixture
    def service(self):
        with patch('src.services.storage.get_settings') as mock_get_settings:
            settings = Mock()
            settings.storage.provider = "local"
            mock_get_settings.return_value = settings
            return StorageService()

    @pytest.mark.asyncio
    async def test_upload_local(self, service, tmp_path):
        """Test local file upload."""
        with patch('src.services.storage.Path') as mock_path:
            mock_base = tmp_path / "data" / "test-bucket"
            mock_path.return_value.__truediv__ = lambda x: mock_base / x
            
            file_data = b"test content"
            result = await service.upload(file_data, "test.txt", "test-bucket")
            
            assert result == "test.txt"

    @pytest.mark.asyncio
    async def test_upload_stream_local(self, service, tmp_path):
        """Test local stream upload."""
        import io
        file_obj = io.BytesIO(b"test content")
        
        with patch('src.services.storage.Path') as mock_path:
            mock_base = tmp_path / "data" / "test-bucket"
            mock_path.return_value.__truediv__ = lambda x: mock_base / x
            
            result = await service.upload_stream(file_obj, "test.txt", "test-bucket")
            
            assert result == "test.txt"


class TestStorageServiceSignedUrlCaching:
    """Test signed URL caching functionality."""

    @pytest.fixture
    def service(self):
        with patch('src.services.storage.get_settings') as mock_get_settings:
            settings = Mock()
            settings.storage.provider = "supabase"
            settings.storage.supabase_url = "https://test.supabase.co"
            settings.storage.supabase_key = "test-key"
            mock_get_settings.return_value = settings
            
            with patch('src.services.storage.create_client') as mock_create_client:
                mock_client = Mock()
                mock_create_client.return_value = mock_client
                service = StorageService()
                service.client = mock_client
                return service

    @pytest.mark.asyncio
    async def test_get_url_private_uses_cache(self, service):
        """Test that private URL generation uses cache."""
        # Mock the storage response
        mock_storage = Mock()
        mock_storage.from_.return_value.create_signed_url.return_value = {
            'signedURL': 'https://test.supabase.co/signed-url-1'
        }
        service.client.storage = mock_storage
        
        # First call should hit Supabase
        result1 = await service.get_url("test.pdf", "test-bucket", private=True)
        assert result1 == 'https://test.supabase.co/signed-url-1'
        
        # Second call should use cache
        result2 = await service.get_url("test.pdf", "test-bucket", private=True)
        assert result2 == 'https://test.supabase.co/signed-url-1'
        
        # create_signed_url should only be called once
        mock_storage.from_.return_value.create_signed_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_url_public_no_cache(self, service):
        """Test that public URL generation doesn't use cache."""
        mock_storage = Mock()
        mock_storage.from_.return_value.get_public_url.return_value = 'https://test.supabase.co/public-url'
        service.client.storage = mock_storage
        
        result = await service.get_url("test.pdf", "test-bucket", private=False)
        
        assert result == 'https://test.supabase.co/public-url'
        mock_storage.from_.return_value.get_public_url.assert_called_once()


class TestGetStorageService:
    """Test get_storage_service function."""

    def test_returns_storage_service(self):
        """Test that get_storage_service returns a StorageService instance."""
        with patch('src.services.storage.get_settings') as mock_get_settings:
            settings = Mock()
            settings.storage.provider = "local"
            mock_get_settings.return_value = settings
            
            service = get_storage_service()
            
            assert isinstance(service, StorageService)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
