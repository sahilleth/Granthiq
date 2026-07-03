"""
Unit tests for database models.

Tests the SQLModel schemas including:
- User model
- Notebook model
- Document model
- ChatMessage model
- GeneratedContent model
- Model relationships and constraints
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from src.db.models import (
    User,
    Notebook,
    Document,
    ChatMessage,
    MessageCitation,
    GeneratedContent,
    ProcessingStatus,
    ContentType
)


class TestUserModel:
    """Test suite for User model."""

    def test_create_user_basic(self):
        """Test creating a basic user."""
        user = User(
            email="test@example.com",
            hashed_password="hashed_password_123"
        )

        assert user.email == "test@example.com"
        assert user.hashed_password == "hashed_password_123"
        assert user.is_active is True  # Default value

    def test_create_user_with_id(self):
        """Test creating a user with explicit ID."""
        user_id = uuid4()
        user = User(
            id=user_id,
            email="test@example.com",
            hashed_password="hashed_password_123"
        )

        assert user.id == user_id

    def test_create_user_inactive(self):
        """Test creating an inactive user."""
        user = User(
            email="inactive@example.com",
            hashed_password="password",
            is_active=False
        )

        assert user.is_active is False

    def test_user_timestamps(self):
        """Test user timestamps are set correctly."""
        now = datetime.now(timezone.utc)
        user = User(
            email="test@example.com",
            hashed_password="password",
            created_at=now
        )

        assert user.created_at == now


class TestNotebookModel:
    """Test suite for Notebook model."""

    def test_create_notebook_basic(self):
        """Test creating a basic notebook."""
        user_id = uuid4()
        notebook = Notebook(
            user_id=user_id,
            title="My Notebook"
        )

        assert notebook.user_id == user_id
        assert notebook.title == "My Notebook"
        assert notebook.settings == {}  # Default

    def test_create_notebook_with_settings(self):
        """Test creating a notebook with custom settings."""
        user_id = uuid4()
        settings = {
            "use_hyde": True,
            "top_k_results": 10,
            "chunking_strategy": "semantic"
        }
        notebook = Notebook(
            user_id=user_id,
            title="Custom Notebook",
            settings=settings
        )

        assert notebook.settings == settings
        assert notebook.settings["use_hyde"] is True
        assert notebook.settings["top_k_results"] == 10

    def test_notebook_default_settings(self):
        """Test notebook has empty settings by default."""
        notebook = Notebook(
            user_id=uuid4(),
            title="Test"
        )

        assert isinstance(notebook.settings, dict)
        assert len(notebook.settings) == 0


class TestDocumentModel:
    """Test suite for Document model."""

    def test_create_document_basic(self):
        """Test creating a basic document."""
        notebook_id = uuid4()
        doc = Document(
            notebook_id=notebook_id,
            filename="test.pdf",
            file_path="uploads/test.pdf",
            mime_type="application/pdf"
        )

        assert doc.notebook_id == notebook_id
        assert doc.filename == "test.pdf"
        assert doc.mime_type == "application/pdf"
        assert doc.status == ProcessingStatus.PENDING  # Default

    def test_document_processing_status_enum(self):
        """Test document status uses ProcessingStatus enum."""
        doc = Document(
            notebook_id=uuid4(),
            filename="test.pdf",
            file_path="path.pdf",
            mime_type="application/pdf",
            status=ProcessingStatus.COMPLETED
        )

        assert doc.status == ProcessingStatus.COMPLETED
        assert doc.status.value == "completed"

    def test_document_with_chunk_count(self):
        """Test document with chunk count."""
        doc = Document(
            notebook_id=uuid4(),
            filename="test.pdf",
            file_path="path.pdf",
            mime_type="application/pdf",
            chunk_count=25
        )

        assert doc.chunk_count == 25

    def test_document_with_error_message(self):
        """Test document with error message."""
        doc = Document(
            notebook_id=uuid4(),
            filename="test.pdf",
            file_path="path.pdf",
            mime_type="application/pdf",
            status=ProcessingStatus.FAILED,
            error_message="Failed to process: invalid format"
        )

        assert doc.status == ProcessingStatus.FAILED
        assert doc.error_message == "Failed to process: invalid format"

    def test_document_with_file_hash(self):
        """Test document with file hash for deduplication."""
        doc = Document(
            notebook_id=uuid4(),
            filename="test.pdf",
            file_path="path.pdf",
            mime_type="application/pdf",
            file_hash="sha256_abc123def456"
        )

        assert doc.file_hash == "sha256_abc123def456"

    def test_document_mime_types(self):
        """Test various document MIME types."""
        mime_types = [
            ("application/pdf", "test.pdf"),
            ("text/plain", "test.txt"),
            ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "test.docx"),
            ("audio/mpeg", "test.mp3")
        ]

        for mime_type, filename in mime_types:
            doc = Document(
                notebook_id=uuid4(),
                filename=filename,
                file_path=f"path/{filename}",
                mime_type=mime_type
            )
            assert doc.mime_type == mime_type


class TestChatMessageModel:
    """Test suite for ChatMessage model."""

    def test_create_user_message(self):
        """Test creating a user message."""
        notebook_id = uuid4()
        msg = ChatMessage(
            notebook_id=notebook_id,
            role="user",
            content="What is the main topic of this document?"
        )

        assert msg.notebook_id == notebook_id
        assert msg.role == "user"
        assert msg.content == "What is the main topic of this document?"

    def test_create_assistant_message(self):
        """Test creating an assistant message."""
        notebook_id = uuid4()
        msg = ChatMessage(
            notebook_id=notebook_id,
            role="assistant",
            content="The main topic is artificial intelligence."
        )

        assert msg.role == "assistant"

    def test_message_with_metadata(self):
        """Test message with metadata."""
        msg = ChatMessage(
            notebook_id=uuid4(),
            role="assistant",
            content="Test response",
            metadata={"model": "gemini-2.5-flash", "tokens": 150}
        )

        assert msg.metadata["model"] == "gemini-2.5-flash"
        assert msg.metadata["tokens"] == 150


class TestMessageCitationModel:
    """Test suite for MessageCitation model."""

    def test_create_citation(self):
        """Test creating a message citation."""
        message_id = uuid4()
        document_id = uuid4()

        citation = MessageCitation(
            message_id=message_id,
            document_id=document_id,
            chunk_id="doc_chunk_0",
            text="This is the cited text from the document.",
            relevance_score=0.85
        )

        assert citation.message_id == message_id
        assert citation.document_id == document_id
        assert citation.chunk_id == "doc_chunk_0"
        assert citation.relevance_score == 0.85

    def test_citation_with_page_number(self):
        """Test citation with page number metadata."""
        citation = MessageCitation(
            message_id=uuid4(),
            document_id=uuid4(),
            chunk_id="doc_chunk_5",
            text="Citation text",
            relevance_score=0.9,
            metadata={"page": 5, "section": "Introduction"}
        )

        assert citation.metadata["page"] == 5


class TestGeneratedContentModel:
    """Test suite for GeneratedContent model."""

    def test_create_podcast_content(self):
        """Test creating podcast content."""
        notebook_id = uuid4()
        content = GeneratedContent(
            notebook_id=notebook_id,
            content_type=ContentType.PODCAST,
            status=ProcessingStatus.COMPLETED,
            content_data={
                "title": "AI Discussion",
                "dialogue": [
                    {"speaker": "Host", "text": "Welcome!"},
                    {"speaker": "Guest", "text": "Thanks!"}
                ]
            }
        )

        assert content.content_type == ContentType.PODCAST
        assert content.content_data["title"] == "AI Discussion"

    def test_create_quiz_content(self):
        """Test creating quiz content."""
        content = GeneratedContent(
            notebook_id=uuid4(),
            content_type=ContentType.QUIZ,
            status=ProcessingStatus.COMPLETED,
            content_data={
                "title": "AI Quiz",
                "questions": [
                    {"question": "What is ML?", "answer": "Machine Learning"}
                ]
            }
        )

        assert content.content_type == ContentType.QUIZ
        assert content.content_type.value == "quiz"

    def test_create_flashcard_content(self):
        """Test creating flashcard content."""
        content = GeneratedContent(
            notebook_id=uuid4(),
            content_type=ContentType.FLASHCARD,
            status=ProcessingStatus.COMPLETED,
            content_data={
                "cards": [
                    {"front": "AI", "back": "Artificial Intelligence"}
                ]
            }
        )

        assert content.content_type == ContentType.FLASHCARD

    def test_create_mindmap_content(self):
        """Test creating mindmap content."""
        content = GeneratedContent(
            notebook_id=uuid4(),
            content_type=ContentType.MINDMAP,
            status=ProcessingStatus.COMPLETED,
            content_data={
                "central_topic": "Machine Learning",
                "nodes": []
            }
        )

        assert content.content_type == ContentType.MINDMAP

    def test_content_with_audio_url(self):
        """Test podcast content with audio URL."""
        content = GeneratedContent(
            notebook_id=uuid4(),
            content_type=ContentType.PODCAST,
            status=ProcessingStatus.COMPLETED,
            content_data={"title": "Test"},
            audio_url="https://storage.example.com/podcast.mp3"
        )

        assert content.audio_url == "https://storage.example.com/podcast.mp3"

    def test_content_linked_to_document(self):
        """Test content linked to specific document."""
        document_id = uuid4()
        content = GeneratedContent(
            notebook_id=uuid4(),
            document_id=document_id,
            content_type=ContentType.QUIZ,
            status=ProcessingStatus.COMPLETED,
            content_data={}
        )

        assert content.document_id == document_id


class TestProcessingStatusEnum:
    """Test ProcessingStatus enum values."""

    def test_all_status_values(self):
        """Test all processing status values are accessible."""
        assert ProcessingStatus.PENDING.value == "pending"
        assert ProcessingStatus.PROCESSING.value == "processing"
        assert ProcessingStatus.COMPLETED.value == "completed"
        assert ProcessingStatus.FAILED.value == "failed"

    def test_status_comparison(self):
        """Test status enum comparisons."""
        assert ProcessingStatus.PENDING != ProcessingStatus.COMPLETED
        assert ProcessingStatus.COMPLETED == ProcessingStatus.COMPLETED


class TestContentTypeEnum:
    """Test ContentType enum values."""

    def test_all_content_types(self):
        """Test all content type values."""
        assert ContentType.PODCAST.value == "podcast"
        assert ContentType.QUIZ.value == "quiz"
        assert ContentType.FLASHCARD.value == "flashcard"
        assert ContentType.MINDMAP.value == "mindmap"

    def test_content_type_from_string(self):
        """Test creating content type from string."""
        assert ContentType("podcast") == ContentType.PODCAST
        assert ContentType("quiz") == ContentType.QUIZ
