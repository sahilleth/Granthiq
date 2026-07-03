"""
Unit tests for service layer business logic.
Tests services with mocked dependencies for isolation.
"""

import sys
from pathlib import Path

# Add backend directory to path for direct execution
_backend_dir = Path(__file__).parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from tests.fixtures.mocks import MockQueryEngine, MockLLM, MockStorageService


class TestChatServiceLogic:
    """Test ChatService business logic."""

    @pytest.fixture
    def mock_query_engine(self):
        """Create mock query engine."""
        return MockQueryEngine(
            default_response="This is a test response based on your documents."
        )

    @pytest.mark.asyncio
    async def test_message_validation_empty(self):
        """Test that empty messages are rejected."""
        from pydantic import ValidationError
        from src.routers.chat import ChatMessageRequest

        with pytest.raises(ValidationError):
            ChatMessageRequest(message="", stream=False)

    @pytest.mark.asyncio
    async def test_message_validation_too_long(self):
        """Test that overly long messages are rejected."""
        from pydantic import ValidationError
        from src.routers.chat import ChatMessageRequest

        long_message = "x" * 10001  # Exceeds 10000 character limit
        with pytest.raises(ValidationError):
            ChatMessageRequest(message=long_message, stream=False)

    @pytest.mark.asyncio
    async def test_message_validation_success(self):
        """Test valid message passes validation."""
        from src.routers.chat import ChatMessageRequest

        msg = ChatMessageRequest(message="What is this document about?", stream=False)
        assert msg.message == "What is this document about?"
        assert msg.stream is False


class TestGenerationServiceLogic:
    """Test GenerationService business logic."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM."""
        return MockLLM(default_response='{"title": "Test Quiz", "questions": []}')

    @pytest.mark.asyncio
    async def test_content_type_validation(self):
        """Test content type validation."""
        from pydantic import ValidationError
        from src.routers.generation import GenerateRequest

        # Valid content types
        valid_types = ["podcast", "quiz", "flashcard", "mindmap"]
        for ct in valid_types:
            req = GenerateRequest(content_type=ct)
            assert req.content_type == ct

        # Invalid content type
        with pytest.raises(ValidationError):
            GenerateRequest(content_type="invalid")

    @pytest.mark.asyncio
    async def test_document_ids_optional(self):
        """Test document_ids is optional."""
        from src.routers.generation import GenerateRequest

        req = GenerateRequest(content_type="quiz")
        assert req.document_ids is None

        req_with_docs = GenerateRequest(
            content_type="quiz",
            document_ids=[uuid4(), uuid4()]
        )
        assert len(req_with_docs.document_ids) == 2


class TestNotebookServiceLogic:
    """Test notebook-related business logic."""

    @pytest.mark.asyncio
    async def test_notebook_create_defaults(self):
        """Test notebook creation with defaults."""
        from src.routers.notebooks import NotebookCreate

        create_data = NotebookCreate()
        assert create_data.title == "Untitled Notebook"
        assert create_data.settings is None

    @pytest.mark.asyncio
    async def test_notebook_create_with_settings(self):
        """Test notebook creation with custom settings."""
        from src.routers.notebooks import NotebookCreate
        from src.schemas.rag_config import NotebookRAGConfig

        settings = NotebookRAGConfig(use_hyde=True, top_k_results=10)
        create_data = NotebookCreate(title="My Notebook", settings=settings)

        assert create_data.title == "My Notebook"
        assert create_data.settings.use_hyde is True
        assert create_data.settings.top_k_results == 10

    @pytest.mark.asyncio
    async def test_notebook_update_partial(self):
        """Test partial notebook updates."""
        from src.routers.notebooks import NotebookUpdate

        # Update only title
        update_title = NotebookUpdate(title="New Title")
        assert update_title.title == "New Title"
        assert update_title.settings is None

        # Update only settings
        from src.schemas.rag_config import NotebookRAGConfig
        settings = NotebookRAGConfig(enable_reranking=False)
        update_settings = NotebookUpdate(settings=settings)
        assert update_settings.title is None
        assert update_settings.settings.enable_reranking is False


class TestAuthServiceLogic:
    """Test authentication service logic."""

    @pytest.mark.asyncio
    async def test_jwt_payload_extraction(self):
        """Test JWT payload extraction logic."""
        import jwt
        from src.config import get_settings

        settings = get_settings()
        if not settings.auth.secret_key:
            pytest.skip("Auth secret key not configured")

        user_id = uuid4()
        email = "test@example.com"

        # Create token
        import time
        payload = {
            "aud": "authenticated",
            "role": "authenticated",
            "sub": str(user_id),
            "email": email,
            "exp": int(time.time()) + 3600
        }
        token = jwt.encode(
            payload,
            settings.auth.secret_key,
            algorithm=settings.auth.algorithm
        )

        # Decode and verify
        decoded = jwt.decode(
            token,
            settings.auth.secret_key,
            algorithms=[settings.auth.algorithm],
            audience="authenticated"
        )

        assert decoded["sub"] == str(user_id)
        assert decoded["email"] == email

    @pytest.mark.asyncio
    async def test_expired_token_detection(self):
        """Test expired token is properly detected."""
        import jwt
        import time
        from src.config import get_settings

        settings = get_settings()
        if not settings.auth.secret_key:
            pytest.skip("Auth secret key not configured")

        # Create expired token
        payload = {
            "aud": "authenticated",
            "sub": str(uuid4()),
            "exp": int(time.time()) - 3600  # Expired 1 hour ago
        }
        token = jwt.encode(
            payload,
            settings.auth.secret_key,
            algorithm=settings.auth.algorithm
        )

        # Should raise ExpiredSignatureError
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(
                token,
                settings.auth.secret_key,
                algorithms=[settings.auth.algorithm],
                audience="authenticated"
            )


class TestStorageServiceLogic:
    """Test storage service logic with mocks."""

    @pytest.mark.asyncio
    async def test_mock_storage_upload(self):
        """Test mock storage upload functionality."""
        import io
        storage = MockStorageService()

        content = b"Test file content"
        file_obj = io.BytesIO(content)

        path = await storage.upload_stream(
            file_obj=file_obj,
            path="test/file.txt",
            bucket="test-bucket",
            mime_type="text/plain"
        )

        assert path == "test/file.txt"
        assert storage.upload_count == 1
        assert "test/file.txt" in storage.files

    @pytest.mark.asyncio
    async def test_mock_storage_get_url(self):
        """Test mock storage URL generation."""
        import io
        storage = MockStorageService()

        # Upload a file first
        await storage.upload_stream(
            file_obj=io.BytesIO(b"content"),
            path="test/file.txt",
            bucket="test-bucket",
            mime_type="text/plain"
        )

        # Get URL
        url = await storage.get_url("test/file.txt", "test-bucket", private=True)

        assert url is not None
        assert "test-bucket" in url
        assert "private_token" in url

    @pytest.mark.asyncio
    async def test_mock_storage_delete(self):
        """Test mock storage deletion."""
        import io
        storage = MockStorageService()

        # Upload a file first
        await storage.upload_stream(
            file_obj=io.BytesIO(b"content"),
            path="test/file.txt",
            bucket="test-bucket",
            mime_type="text/plain"
        )

        # Delete
        result = storage.delete("test/file.txt", "test-bucket")

        assert result is True
        assert storage.delete_count == 1
        assert "test/file.txt" not in storage.files


class TestQueryEngineLogic:
    """Test query engine logic with mocks."""

    @pytest.mark.asyncio
    async def test_mock_query_engine_response(self):
        """Test mock query engine returns expected response."""
        engine = MockQueryEngine(default_response="Test response text")

        query_bundle = MagicMock()
        query_bundle.query_str = "What is this about?"

        response = await engine.aquery(query_bundle)

        assert response.response == "Test response text"
        assert len(engine.queries) == 1

    @pytest.mark.asyncio
    async def test_mock_query_engine_streaming(self):
        """Test mock query engine streaming."""
        engine = MockQueryEngine(default_response="This is a streaming response")

        tokens = []
        async for token in engine.stream_query("What is this?"):
            tokens.append(token)

        result = "".join(tokens)
        assert "streaming" in result.lower()

    @pytest.mark.asyncio
    async def test_mock_query_engine_failure(self):
        """Test mock query engine failure mode."""
        engine = MockQueryEngine()
        engine.set_failure(True, "Connection failed")

        with pytest.raises(Exception) as exc_info:
            await engine.aquery(MagicMock())

        assert "Connection failed" in str(exc_info.value)


class TestRAGConfigMerging:
    """Test RAG configuration merging logic."""

    @pytest.mark.asyncio
    async def test_merge_rag_settings_empty_notebook(self):
        """Test merging when notebook has no settings."""
        from src.utils.rag_config import merge_rag_settings
        from src.config import RagSettings

        global_settings = RagSettings(
            use_hyde=True,
            top_k_results=5,
            enable_reranking=True
        )

        merged = merge_rag_settings({}, global_settings)

        # Should use global defaults
        assert merged.use_hyde is True
        assert merged.top_k_results == 5
        assert merged.enable_reranking is True

    @pytest.mark.asyncio
    async def test_merge_rag_settings_notebook_override(self):
        """Test notebook settings override global settings."""
        from src.utils.rag_config import merge_rag_settings
        from src.config import RagSettings

        global_settings = RagSettings(
            use_hyde=True,
            top_k_results=5
        )

        notebook_settings = {
            "use_hyde": False,
            "top_k_results": 10
        }

        merged = merge_rag_settings(notebook_settings, global_settings)

        # Should use notebook overrides
        assert merged.use_hyde is False
        assert merged.top_k_results == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
