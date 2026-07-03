"""
Unit tests for Qdrant vector store operations.
Tests collection management, node operations, and error handling.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4
import numpy as np

from llama_index.core.schema import TextNode
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import CollectionInfo, VectorParams, Distance

from src.db.vector_store import QdrantVectorStoreWrapper, get_vector_store
from src.utils.exceptions import VectorStoreError


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.qdrant.host = None  # Use local storage
    settings.qdrant.collection_name = "test_collection"
    settings.qdrant.api_key = None
    settings.embedding.dimension = 384
    settings.embedding.model = "all-MiniLM-L6-v2"
    return settings


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client for testing."""
    client = Mock()
    client.get_collection = Mock()
    client.create_collection = Mock()
    client.delete_collection = Mock()
    client.upsert = Mock()
    client.search = Mock()
    client.create_payload_index = Mock()
    return client


class TestQdrantVectorStoreWrapper:
    """Test QdrantVectorStoreWrapper class."""

    def test_collection_exists_true(self, mock_settings, mock_qdrant_client):
        """Test collection_exists returns True when collection exists."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient', return_value=mock_qdrant_client):
                wrapper = QdrantVectorStoreWrapper()
                wrapper.client = mock_qdrant_client
                wrapper.collection_name = "test_collection"
                
                # Mock successful collection retrieval
                mock_qdrant_client.get_collection.return_value = Mock()
                
                assert wrapper.collection_exists() is True
                mock_qdrant_client.get_collection.assert_called_once_with("test_collection")

    def test_collection_exists_false(self, mock_settings, mock_qdrant_client):
        """Test collection_exists returns False when collection doesn't exist."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient', return_value=mock_qdrant_client):
                wrapper = QdrantVectorStoreWrapper()
                wrapper.client = mock_qdrant_client
                wrapper.collection_name = "test_collection"
                
                # Mock collection not found
                mock_qdrant_client.get_collection.side_effect = UnexpectedResponse(
                    text="Collection not found",
                    status_code=404
                )
                
                assert wrapper.collection_exists() is False

    def test_get_collection_info_success(self, mock_settings, mock_qdrant_client):
        """Test get_collection_info returns info when collection exists."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient', return_value=mock_qdrant_client):
                wrapper = QdrantVectorStoreWrapper()
                wrapper.client = mock_qdrant_client
                wrapper.collection_name = "test_collection"
                
                mock_info = Mock(spec=CollectionInfo)
                mock_qdrant_client.get_collection.return_value = mock_info
                
                result = wrapper.get_collection_info()
                
                assert result == mock_info

    def test_get_collection_info_not_found(self, mock_settings, mock_qdrant_client):
        """Test get_collection_info returns None when collection doesn't exist."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient', return_value=mock_qdrant_client):
                wrapper = QdrantVectorStoreWrapper()
                wrapper.client = mock_qdrant_client
                wrapper.collection_name = "test_collection"
                
                mock_qdrant_client.get_collection.side_effect = UnexpectedResponse(
                    text="Collection not found",
                    status_code=404
                )
                
                result = wrapper.get_collection_info()
                
                assert result is None

    def test_delete_collection_success(self, mock_settings, mock_qdrant_client):
        """Test delete_collection returns True on success."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient', return_value=mock_qdrant_client):
                wrapper = QdrantVectorStoreWrapper()
                wrapper.client = mock_qdrant_client
                wrapper.collection_name = "test_collection"
                
                result = wrapper.delete_collection()
                
                assert result is True
                mock_qdrant_client.delete_collection.assert_called_once_with("test_collection")

    def test_delete_collection_failure(self, mock_settings, mock_qdrant_client):
        """Test delete_collection returns False on failure."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient', return_value=mock_qdrant_client):
                wrapper = QdrantVectorStoreWrapper()
                wrapper.client = mock_qdrant_client
                wrapper.collection_name = "test_collection"
                
                mock_qdrant_client.delete_collection.side_effect = Exception("Delete failed")
                
                result = wrapper.delete_collection()
                
                assert result is False

    def test_add_nodes_empty_list(self, mock_settings, mock_qdrant_client):
        """Test add_nodes with empty list returns empty list."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient', return_value=mock_qdrant_client):
                wrapper = QdrantVectorStoreWrapper()
                wrapper.client = mock_qdrant_client
                wrapper.collection_name = "test_collection"
                
                result = wrapper.add_nodes([])
                
                assert result == []

    def test_add_nodes_with_nodes(self, mock_settings, mock_qdrant_client):
        """Test add_nodes with valid nodes."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient', return_value=mock_qdrant_client):
                with patch.object(QdrantVectorStoreWrapper, '_ensure_collection_exists'):
                    wrapper = QdrantVectorStoreWrapper()
                    wrapper.client = mock_qdrant_client
                    wrapper.collection_name = "test_collection"
                    wrapper.embedding_model = Mock()
                    wrapper.embedding_model.encode.return_value = np.array([[0.1] * 384])
                    wrapper.embed_model = None
                    
                    # Mock collection info for vector name detection
                    mock_info = Mock()
                    mock_info.config.params.vectors = None
                    mock_qdrant_client.get_collection.return_value = mock_info
                    
                    nodes = [
                        TextNode(
                            id_=str(uuid4()),
                            text="Test content",
                            metadata={"test": "value"}
                        )
                    ]
                    
                    result = wrapper.add_nodes(nodes)
                    
                    assert len(result) == 1
                    mock_qdrant_client.upsert.assert_called_once()

    def test_build_qdrant_filter_empty(self, mock_settings, mock_qdrant_client):
        """Test _build_qdrant_filter with empty filter dict."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient', return_value=mock_qdrant_client):
                wrapper = QdrantVectorStoreWrapper()
                
                result = wrapper._build_qdrant_filter({})
                
                assert result is None

    def test_build_qdrant_filter_with_conditions(self, mock_settings, mock_qdrant_client):
        """Test _build_qdrant_filter with filter conditions."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient', return_value=mock_qdrant_client):
                wrapper = QdrantVectorStoreWrapper()
                
                filter_dict = {
                    "notebook_id": "test-notebook-id",
                    "document_id": "test-doc-id"
                }
                
                result = wrapper._build_qdrant_filter(filter_dict)
                
                assert result is not None
                assert len(result.must) == 2


class TestGetVectorStore:
    """Test get_vector_store function."""

    @patch('src.db.vector_store._vector_store_instance', None)
    def test_get_vector_store_singleton(self, mock_settings):
        """Test get_vector_store returns singleton instance."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient'):
                with patch.object(QdrantVectorStoreWrapper, '_ensure_collection_exists'):
                    # First call should create instance
                    instance1 = get_vector_store()
                    # Second call should return same instance
                    instance2 = get_vector_store()
                    
                    assert instance1 is instance2


class TestErrorHandling:
    """Test error handling in vector store operations."""

    def test_unexpected_response_handling(self, mock_settings, mock_qdrant_client):
        """Test handling of UnexpectedResponse exceptions."""
        with patch('src.db.vector_store.get_settings', return_value=mock_settings):
            with patch('src.db.vector_store.QdrantClient', return_value=mock_qdrant_client):
                wrapper = QdrantVectorStoreWrapper()
                wrapper.client = mock_qdrant_client
                wrapper.collection_name = "test_collection"
                
                # Test various error codes
                mock_qdrant_client.get_collection.side_effect = UnexpectedResponse(
                    text="Not found",
                    status_code=404
                )
                
                assert wrapper.collection_exists() is False
                assert wrapper.get_collection_info() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
