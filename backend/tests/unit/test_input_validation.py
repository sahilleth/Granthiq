"""
Tests for input validation and size limits.
"""

import pytest
from pydantic import ValidationError
from src.schemas.chat import ChatMessageRequest, PromptEnhanceRequest
from src.schemas.documents import ProcessUrlRequest
from src.schemas.notes import NoteCreate, NoteUpdate
from src.schemas.content import GenerationCreate
from src.schemas.notebooks import NotebookCreate


class TestChatInputValidation:
    """Tests for chat message input validation."""

    def test_chat_message_valid_length(self):
        """Test valid message lengths."""
        # Minimum length (1 char)
        req = ChatMessageRequest(message="a")
        assert req.message == "a"

        # Maximum length (10000 chars)
        req = ChatMessageRequest(message="x" * 10000)
        assert len(req.message) == 10000

    def test_chat_message_too_short(self):
        """Test that empty message is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChatMessageRequest(message="")
        assert "Input too short" in str(exc_info.value) or "min_length" in str(
            exc_info.value
        )

    def test_chat_message_too_long(self):
        """Test that message exceeding max length is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChatMessageRequest(message="x" * 10001)
        assert "Input too long" in str(exc_info.value) or "max_length" in str(
            exc_info.value
        )

    def test_prompt_enhance_valid_length(self):
        """Test PromptEnhanceRequest validation."""
        req = PromptEnhanceRequest(message="Test message")
        assert req.message == "Test message"

        # Max length
        req = PromptEnhanceRequest(message="x" * 5000)
        assert len(req.message) == 5000

    def test_prompt_enhance_too_long(self):
        """Test that prompt exceeding 5000 chars is rejected."""
        with pytest.raises(ValidationError):
            PromptEnhanceRequest(message="x" * 5001)


class TestDocumentInputValidation:
    """Tests for document input validation."""

    def test_process_url_valid_length(self):
        """Test valid URL lengths."""
        req = ProcessUrlRequest(url="https://example.com")
        assert req.url == "https://example.com"

        # Max length URL
        long_url = "https://example.com/" + "a" * 2000
        req = ProcessUrlRequest(url=long_url)
        assert len(req.url) == 2048 + 17  # base + 2000

    def test_process_url_too_long(self):
        """Test that URL exceeding 2048 chars is rejected."""
        with pytest.raises(ValidationError):
            ProcessUrlRequest(url="https://example.com/" + "a" * 2000 + "extra")


class TestNotesInputValidation:
    """Tests for notes input validation."""

    def test_note_title_valid_length(self):
        """Test valid note title lengths."""
        req = NoteCreate(title="A", content="Test content")
        assert req.title == "A"

        # Max length
        req = NoteCreate(title="x" * 500, content="Test")
        assert len(req.title) == 500

    def test_note_title_too_long(self):
        """Test that title exceeding 500 chars is rejected."""
        with pytest.raises(ValidationError):
            NoteCreate(title="x" * 501, content="Test")

    def test_note_content_valid_length(self):
        """Test valid note content lengths."""
        req = NoteCreate(title="Test", content="")
        assert req.content == ""

        # Max length (50000)
        req = NoteCreate(title="Test", content="x" * 50000)
        assert len(req.content) == 50000

    def test_note_content_too_long(self):
        """Test that content exceeding 50000 chars is rejected."""
        with pytest.raises(ValidationError):
            NoteCreate(title="Test", content="x" * 50001)

    def test_note_update_validation(self):
        """Test NoteUpdate validation."""
        req = NoteUpdate(title="New Title")
        assert req.title == "New Title"

        req = NoteUpdate(content="New Content")
        assert req.content == "New Content"


class TestGenerationInputValidation:
    """Tests for generation input validation."""

    def test_generation_title_valid_length(self):
        """Test valid generation title lengths."""
        req = GenerationCreate(title="A", content="Test content")
        assert req.title == "A"

        # Max length
        req = GenerationCreate(title="x" * 500, content="Test")
        assert len(req.title) == 500

    def test_generation_title_too_long(self):
        """Test that title exceeding 500 chars is rejected."""
        with pytest.raises(ValidationError):
            GenerationCreate(title="x" * 501, content="Test")

    def test_generation_content_valid_length(self):
        """Test valid generation content (max 100KB)."""
        req = GenerationCreate(title="Test", content="x" * 102400)
        assert len(req.content) == 102400

    def test_generation_content_too_long(self):
        """Test that content exceeding 100KB is rejected."""
        with pytest.raises(ValidationError):
            GenerationCreate(title="Test", content="x" * 102401)


class TestNotebookInputValidation:
    """Tests for notebook input validation."""

    def test_notebook_title_valid_length(self):
        """Test valid notebook title lengths."""
        req = NotebookCreate(title="A")
        assert req.title == "A"

        # Max length
        req = NotebookCreate(title="x" * 255)
        assert len(req.title) == 255

    def test_notebook_title_too_long(self):
        """Test that title exceeding 255 chars is rejected."""
        with pytest.raises(ValidationError):
            NotebookCreate(title="x" * 256)

    def test_notebook_title_too_short(self):
        """Test that empty title is rejected."""
        with pytest.raises(ValidationError):
            NotebookCreate(title="")
