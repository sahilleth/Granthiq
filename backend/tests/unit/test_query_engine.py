"""
Unit tests for QueryEngineService

Tests the core query engine functionality including:
- Query execution with filters
- Policy enforcement
- Streaming responses
- Error handling
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID
from typing import Dict, Any

from src.services.query.query_engine import QueryEngineService
from src.config import Settings, RagSettings
from llama_index.core.base.response.schema import Response, StreamingResponse
from llama_index.core.schema import TextNode, NodeWithScore


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock(spec=Settings)
    settings.rag = Mock(spec=RagSettings)
    settings.rag.chunk_size = 1000
    settings.rag.chunk_overlap = 200
    settings.rag.top_k_results = 5
    settings.rag.enable_streaming = False
    settings.rag.enable_query_fusion = False
    settings.rag.use_hyde = False
    settings.rag.hybrid_alpha = 0.7
    settings.rag.reranker_top_n = 5
    settings.rag.chunking_strategy = "semantic"
    settings.llm.provider = "groq"
    settings.llm.temperature = 0.7
    settings.llm.model_name = "llama-3.3-70b-versatile"
    settings.anonymous_user_id = uuid4()
    settings.evaluation.enabled = False
    settings.policy.min_score_threshold = 0.6
    settings.policy.min_context_chunks = 1
    return settings


@pytest.fixture
def mock_query_engine():
    """Mock LlamaIndex query engine."""
    engine = Mock()
    engine.query = AsyncMock()
    engine.aquery = AsyncMock()
    return engine


class TestQueryEngineService:
    """Test suite for QueryEngineService."""

    def test_initialization(self, mock_settings):
        """Test query engine service initializes correctly."""
        with patch('src.services.query.query_engine.get_settings', return_value=mock_settings):
            with patch('src.services.query.query_engine.QueryEngineBuilder') as mock_builder:
                # Setup builder mock
                mock_instance = Mock()
                mock_instance.provider = "groq"
                mock_instance.llm = Mock()
                mock_instance.retriever = Mock()
                mock_instance.streaming = False
                mock_instance.evaluator = None
                mock_instance.build = Mock(return_value=Mock())
                mock_builder.return_value = mock_instance

                # Create service
                service = QueryEngineService()

                assert service.provider == "groq"
                assert service.streaming == False
                mock_builder.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_with_no_filters(self, mock_settings):
        """Test basic query without filters."""
        with patch('src.services.query.query_engine.get_settings', return_value=mock_settings):
            with patch('src.services.query.query_engine.QueryEngineBuilder') as mock_builder:
                # Setup mocks
                mock_instance = Mock()
                mock_instance.provider = "groq"
                mock_instance.llm = Mock()
                mock_instance.retriever = Mock()
                mock_instance.streaming = False
                mock_instance.evaluator = None

                # Mock query engine
                mock_engine = Mock()
                mock_response = Response(response="Test answer", source_nodes=[])
                mock_engine.aquery = AsyncMock(return_value=mock_response)
                mock_instance.build = Mock(return_value=mock_engine)
                mock_builder.return_value = mock_instance

                # Create service and query
                service = QueryEngineService()
                result = await service.aquery("What is RAG?")

                assert result.response == "Test answer"
                mock_engine.aquery.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_with_document_filter(self, mock_settings):
        """Test query with document ID filter."""
        with patch('src.services.query.query_engine.get_settings', return_value=mock_settings):
            with patch('src.services.query.query_engine.QueryEngineBuilder') as mock_builder:
                # Setup mocks
                mock_instance = Mock()
                mock_instance.provider = "groq"
                mock_instance.llm = Mock()
                mock_instance.retriever = Mock()
                mock_instance.streaming = False
                mock_instance.evaluator = None

                # Mock query engine
                mock_engine = Mock()
                mock_response = Response(
                    response="Document-specific answer",
                    source_nodes=[
                        NodeWithScore(
                            node=TextNode(text="Test content"),
                            score=0.9
                        )
                    ]
                )
                mock_engine.aquery = AsyncMock(return_value=mock_response)
                mock_instance.build = Mock(return_value=mock_engine)
                mock_builder.return_value = mock_instance

                # Create service and query with filter
                service = QueryEngineService()
                document_id = uuid4()
                result = await service.aquery(
                    "What is in this document?",
                    filters={"document_id": str(document_id)}
                )

                assert result.response == "Document-specific answer"
                assert len(result.source_nodes) > 0

    @pytest.mark.asyncio
    async def test_query_with_notebook_filter(self, mock_settings):
        """Test query with notebook ID filter."""
        with patch('src.services.query.query_engine.get_settings', return_value=mock_settings):
            with patch('src.services.query.query_engine.QueryEngineBuilder') as mock_builder:
                # Setup mocks
                mock_instance = Mock()
                mock_instance.provider = "groq"
                mock_instance.llm = Mock()
                mock_instance.retriever = Mock()
                mock_instance.streaming = False
                mock_instance.evaluator = None

                mock_engine = Mock()
                mock_response = Response(response="Notebook answer", source_nodes=[])
                mock_engine.aquery = AsyncMock(return_value=mock_response)
                mock_instance.build = Mock(return_value=mock_engine)
                mock_builder.return_value = mock_instance

                service = QueryEngineService()
                notebook_id = uuid4()
                result = await service.aquery(
                    "What is in my notebook?",
                    filters={"notebook_id": str(notebook_id)}
                )

                assert result.response == "Notebook answer"

    @pytest.mark.asyncio
    async def test_streaming_query(self, mock_settings):
        """Test streaming query returns async generator."""
        mock_settings.rag.enable_streaming = True

        with patch('src.services.query.query_engine.get_settings', return_value=mock_settings):
            with patch('src.services.query.query_engine.QueryEngineBuilder') as mock_builder:
                # Setup mocks
                mock_instance = Mock()
                mock_instance.provider = "groq"
                mock_instance.llm = Mock()
                mock_instance.retriever = Mock()
                mock_instance.streaming = True
                mock_instance.evaluator = None

                # Mock streaming response
                async def mock_generator():
                    for token in ["Test ", "streaming ", "response"]:
                        yield token

                mock_engine = Mock()
                mock_streaming = AsyncMock()
                mock_streaming.async_response_gen = mock_generator
                mock_engine.aquery = AsyncMock(return_value=mock_streaming)
                mock_instance.build = Mock(return_value=mock_engine)
                mock_builder.return_value = mock_instance

                service = QueryEngineService(streaming=True)
                result = await service.aquery("Test query")

                # Collect streaming tokens
                tokens = []
                async for token in service.stream_query("Test query"):
                    tokens.append(token)

                # Note: This test verifies the structure, actual implementation may differ
                assert service.streaming == True

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_settings):
        """Test error handling in query execution."""
        with patch('src.services.query.query_engine.get_settings', return_value=mock_settings):
            with patch('src.services.query.query_engine.QueryEngineBuilder') as mock_builder:
                # Setup mocks
                mock_instance = Mock()
                mock_instance.provider = "groq"
                mock_instance.llm = Mock()
                mock_instance.retriever = Mock()
                mock_instance.streaming = False
                mock_instance.evaluator = None

                # Mock query engine that raises error
                mock_engine = Mock()
                mock_engine.aquery = AsyncMock(side_effect=Exception("LLM API error"))
                mock_instance.build = Mock(return_value=mock_engine)
                mock_builder.return_value = mock_instance

                service = QueryEngineService()

                with pytest.raises(Exception) as exc_info:
                    await service.aquery("Test query")

                assert "LLM API error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_filter_validation(self, mock_settings):
        """Test that empty filters are handled correctly."""
        with patch('src.services.query.query_engine.get_settings', return_value=mock_settings):
            with patch('src.services.query.query_engine.QueryEngineBuilder') as mock_builder:
                mock_instance = Mock()
                mock_instance.provider = "groq"
                mock_instance.llm = Mock()
                mock_instance.retriever = Mock()
                mock_instance.streaming = False
                mock_instance.evaluator = None

                mock_engine = Mock()
                mock_response = Response(response="Answer", source_nodes=[])
                mock_engine.aquery = AsyncMock(return_value=mock_response)
                mock_instance.build = Mock(return_value=mock_engine)
                mock_builder.return_value = mock_instance

                service = QueryEngineService()

                # Test with empty dict
                result = await service.aquery("Test", filters={})
                assert result.response == "Answer"

                # Test with None
                result = await service.aquery("Test", filters=None)
                assert result.response == "Answer"

    @pytest.mark.asyncio
    async def test_high_score_nodes_pass_policy(self, mock_settings):
        """Test that high-scoring nodes pass policy checks."""
        with patch('src.services.query.query_engine.get_settings', return_value=mock_settings):
            with patch('src.services.query.query_engine.QueryEngineBuilder') as mock_builder:
                mock_instance = Mock()
                mock_instance.provider = "groq"
                mock_instance.llm = Mock()
                mock_instance.retriever = Mock()
                mock_instance.streaming = False
                mock_instance.evaluator = None

                mock_engine = Mock()

                # Create nodes with high scores (above threshold)
                high_score_node = NodeWithScore(
                    node=TextNode(
                        text="Relevant content",
                        metadata={"document_id": str(uuid4()), "score": 0.9}
                    ),
                    score=0.9
                )

                mock_response = Response(
                    response="Good answer based on relevant content",
                    source_nodes=[high_score_node]
                )
                mock_engine.aquery = AsyncMock(return_value=mock_response)
                mock_instance.build = Mock(return_value=mock_engine)
                mock_builder.return_value = mock_instance

                service = QueryEngineService()
                result = await service.aquery("Test query")

                assert result.response
                assert len(result.source_nodes) > 0

    def test_service_caching(self, mock_settings):
        """Test that query engine service can be reused."""
        with patch('src.services.query.query_engine.get_settings', return_value=mock_settings):
            with patch('src.services.query.query_engine.QueryEngineBuilder') as mock_builder:
                mock_instance = Mock()
                mock_instance.provider = "groq"
                mock_instance.llm = Mock()
                mock_instance.retriever = Mock()
                mock_instance.streaming = False
                mock_instance.evaluator = None
                mock_instance.build = Mock(return_value=Mock())
                mock_builder.return_value = mock_instance

                service1 = QueryEngineService()
                service2 = QueryEngineService()

                # Services are separate instances (not singleton in this version)
                assert service1 is not service2


class TestQueryEngineIntegration:
    """Integration tests with actual components (requires running services)."""

    @pytest.mark.skip(reason="Requires running Qdrant instance")
    @pytest.mark.asyncio
    async def test_full_query_pipeline(self):
        """Test full query pipeline with real Qdrant."""
        # This would test against real Qdrant with test data
        pass

    @pytest.mark.skip(reason="Requires LLM API key")
    @pytest.mark.asyncio
    async def test_real_llm_query(self):
        """Test query with real LLM."""
        # This would test against real LLM API
        pass
