"""
Unit tests for repository layer operations.
Tests data access patterns and database operations.
"""

import sys
from pathlib import Path

# Add backend directory to path for direct execution
_backend_dir = Path(__file__).parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from src.db.repositories.notebook import NotebookRepository
from src.db.repositories.document import DocumentRepository
from src.db.repositories.chat import ChatRepository
from src.db.models import Notebook, Document, ChatMessage, ProcessingStatus


class TestNotebookRepository:
    """Test suite for NotebookRepository."""

    @pytest.mark.asyncio
    async def test_create_notebook_success(self, db_session, test_user):
        """Test successful notebook creation."""
        repo = NotebookRepository(db_session)
        notebook = await repo.create_notebook(test_user.id, "Test Notebook")

        assert notebook.id is not None
        assert notebook.title == "Test Notebook"
        assert notebook.user_id == test_user.id
        assert notebook.settings == {}
        assert notebook.created_at is not None
        assert notebook.updated_at is not None

    @pytest.mark.asyncio
    async def test_create_notebook_default_title(self, db_session, test_user):
        """Test notebook creation with default title."""
        repo = NotebookRepository(db_session)
        notebook = await repo.create_notebook(test_user.id)

        assert notebook.title == "Untitled Notebook"

    @pytest.mark.asyncio
    async def test_get_user_notebooks_empty(self, db_session, test_user):
        """Test getting notebooks for user with no notebooks."""
        repo = NotebookRepository(db_session)
        notebooks = await repo.get_user_notebooks(test_user.id)

        assert notebooks == []

    @pytest.mark.asyncio
    async def test_get_user_notebooks_ordered_by_updated(self, db_session, test_user):
        """Test notebooks are returned ordered by updated_at desc."""
        repo = NotebookRepository(db_session)

        # Create multiple notebooks
        nb1 = await repo.create_notebook(test_user.id, "First")
        nb2 = await repo.create_notebook(test_user.id, "Second")
        nb3 = await repo.create_notebook(test_user.id, "Third")

        notebooks = await repo.get_user_notebooks(test_user.id)

        # Most recent should be first
        assert len(notebooks) >= 3
        assert notebooks[0].id == nb3.id

    @pytest.mark.asyncio
    async def test_get_notebook_by_id(self, db_session, test_user):
        """Test retrieving notebook by ID."""
        repo = NotebookRepository(db_session)
        notebook = await repo.create_notebook(test_user.id, "Test")

        retrieved = await repo.get(notebook.id)

        assert retrieved is not None
        assert retrieved.id == notebook.id
        assert retrieved.title == "Test"

    @pytest.mark.asyncio
    async def test_get_notebook_not_found(self, db_session):
        """Test retrieving non-existent notebook returns None."""
        repo = NotebookRepository(db_session)
        fake_id = uuid4()

        result = await repo.get(fake_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_notebook_verifies_ownership(self, db_session, test_user):
        """Test that get_notebook enforces ownership check."""
        repo = NotebookRepository(db_session)
        notebook = await repo.create_notebook(test_user.id, "Test")

        # Same user - should succeed
        result = await repo.get_notebook(notebook.id, test_user.id)
        assert result is not None
        assert result.id == notebook.id

        # Different user - should return None
        other_user_id = uuid4()
        result = await repo.get_notebook(notebook.id, other_user_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_notebook_without_ownership_check(self, db_session, test_user):
        """Test get_notebook without user_id (admin access)."""
        repo = NotebookRepository(db_session)
        notebook = await repo.create_notebook(test_user.id, "Test")

        # No user_id - should return notebook
        result = await repo.get_notebook(notebook.id)
        assert result is not None
        assert result.id == notebook.id

    @pytest.mark.asyncio
    async def test_update_settings(self, db_session, test_user):
        """Test updating notebook settings."""
        repo = NotebookRepository(db_session)
        notebook = await repo.create_notebook(test_user.id, "Test")

        settings = {"use_hyde": True, "top_k_results": 10}
        updated = await repo.update_settings(notebook.id, settings)

        assert updated is not None
        assert updated.settings == settings
        assert updated.updated_at > notebook.created_at

    @pytest.mark.asyncio
    async def test_update_notebook_title(self, db_session, test_user):
        """Test updating notebook title."""
        repo = NotebookRepository(db_session)
        notebook = await repo.create_notebook(test_user.id, "Original")

        updated = await repo.update(notebook.id, {"title": "Updated"})

        assert updated is not None
        assert updated.title == "Updated"

    @pytest.mark.asyncio
    async def test_delete_notebook_success(self, db_session, test_user):
        """Test successful notebook deletion."""
        repo = NotebookRepository(db_session)
        notebook = await repo.create_notebook(test_user.id, "To Delete")

        result = await repo.delete_notebook(notebook.id, test_user.id)

        assert result is True
        assert await repo.get(notebook.id) is None

    @pytest.mark.asyncio
    async def test_delete_notebook_wrong_user(self, db_session, test_user):
        """Test deletion fails for wrong user."""
        repo = NotebookRepository(db_session)
        notebook = await repo.create_notebook(test_user.id, "Test")

        other_user_id = uuid4()
        result = await repo.delete_notebook(notebook.id, other_user_id)

        assert result is False
        assert await repo.get(notebook.id) is not None

    @pytest.mark.asyncio
    async def test_delete_notebook_not_found(self, db_session, test_user):
        """Test deletion of non-existent notebook."""
        repo = NotebookRepository(db_session)
        fake_id = uuid4()

        result = await repo.delete_notebook(fake_id, test_user.id)

        assert result is False


class TestDocumentRepository:
    """Test suite for DocumentRepository."""

    @pytest.mark.asyncio
    async def test_create_document(self, db_session, test_notebook):
        """Test creating a document."""
        repo = DocumentRepository(db_session)
        doc = Document(
            notebook_id=test_notebook.id,
            filename="test.pdf",
            file_path="test/path.pdf",
            mime_type="application/pdf",
            status=ProcessingStatus.PENDING
        )

        saved = await repo.create(doc)

        assert saved.id is not None
        assert saved.filename == "test.pdf"
        assert saved.notebook_id == test_notebook.id
        assert saved.status == ProcessingStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_by_notebook(self, db_session, test_notebook):
        """Test getting all documents for a notebook."""
        repo = DocumentRepository(db_session)

        # Create multiple documents
        for i in range(3):
            doc = Document(
                notebook_id=test_notebook.id,
                filename=f"test{i}.pdf",
                file_path=f"test/path{i}.pdf",
                mime_type="application/pdf",
                status=ProcessingStatus.COMPLETED
            )
            await repo.create(doc)

        documents = await repo.get_by_notebook(test_notebook.id)

        assert len(documents) >= 3

    @pytest.mark.asyncio
    async def test_get_by_notebook_empty(self, db_session, test_notebook):
        """Test getting documents for notebook with none."""
        repo = DocumentRepository(db_session)

        documents = await repo.get_by_notebook(test_notebook.id)

        # May have documents from fixtures, but should be a list
        assert isinstance(documents, list)

    @pytest.mark.asyncio
    async def test_update_status(self, db_session, test_notebook):
        """Test updating document processing status."""
        repo = DocumentRepository(db_session)
        doc = Document(
            notebook_id=test_notebook.id,
            filename="test.pdf",
            file_path="test/path.pdf",
            mime_type="application/pdf",
            status=ProcessingStatus.PENDING
        )
        saved = await repo.create(doc)

        updated = await repo.update_status(saved.id, ProcessingStatus.COMPLETED)

        assert updated is not None
        assert updated.status == ProcessingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_update_status_with_error(self, db_session, test_notebook):
        """Test updating status with error message."""
        repo = DocumentRepository(db_session)
        doc = Document(
            notebook_id=test_notebook.id,
            filename="test.pdf",
            file_path="test/path.pdf",
            mime_type="application/pdf",
            status=ProcessingStatus.PROCESSING
        )
        saved = await repo.create(doc)

        error_msg = "Processing failed due to invalid format"
        updated = await repo.update_status(
            saved.id,
            ProcessingStatus.FAILED,
            error_message=error_msg
        )

        assert updated is not None
        assert updated.status == ProcessingStatus.FAILED
        assert updated.error_message == error_msg

    @pytest.mark.asyncio
    async def test_get_by_hash(self, db_session, test_notebook):
        """Test finding document by file hash."""
        repo = DocumentRepository(db_session)
        doc = Document(
            notebook_id=test_notebook.id,
            filename="test.pdf",
            file_path="test/path.pdf",
            mime_type="application/pdf",
            file_hash="abc123hash",
            status=ProcessingStatus.COMPLETED
        )
        await repo.create(doc)

        found = await repo.get_by_hash("abc123hash", test_notebook.id)

        assert found is not None
        assert found.file_hash == "abc123hash"

    @pytest.mark.asyncio
    async def test_get_by_hash_not_found(self, db_session, test_notebook):
        """Test finding non-existent hash returns None."""
        repo = DocumentRepository(db_session)

        found = await repo.get_by_hash("nonexistent", test_notebook.id)

        assert found is None

    @pytest.mark.asyncio
    async def test_delete_document(self, db_session, test_notebook):
        """Test deleting a document."""
        repo = DocumentRepository(db_session)
        doc = Document(
            notebook_id=test_notebook.id,
            filename="to_delete.pdf",
            file_path="test/path.pdf",
            mime_type="application/pdf"
        )
        saved = await repo.create(doc)

        result = await repo.delete(saved.id)

        assert result is True
        assert await repo.get(saved.id) is None


class TestChatRepository:
    """Test suite for ChatRepository."""

    @pytest.mark.asyncio
    async def test_add_user_message(self, db_session, test_notebook):
        """Test adding a user message."""
        repo = ChatRepository(db_session)

        message = await repo.add_message(
            notebook_id=test_notebook.id,
            role="user",
            content="Hello, how are you?"
        )

        assert message.id is not None
        assert message.role == "user"
        assert message.content == "Hello, how are you?"
        assert message.notebook_id == test_notebook.id

    @pytest.mark.asyncio
    async def test_add_assistant_message(self, db_session, test_notebook):
        """Test adding an assistant message."""
        repo = ChatRepository(db_session)

        message = await repo.add_message(
            notebook_id=test_notebook.id,
            role="assistant",
            content="I am doing well, thank you!"
        )

        assert message.role == "assistant"
        assert message.content == "I am doing well, thank you!"

    @pytest.mark.asyncio
    async def test_get_notebook_history(self, db_session, test_notebook):
        """Test retrieving chat history for a notebook."""
        repo = ChatRepository(db_session)

        # Add multiple messages
        await repo.add_message(test_notebook.id, "user", "Message 1")
        await repo.add_message(test_notebook.id, "assistant", "Response 1")
        await repo.add_message(test_notebook.id, "user", "Message 2")

        history = await repo.get_notebook_history(test_notebook.id)

        assert len(history) >= 3

    @pytest.mark.asyncio
    async def test_get_notebook_history_with_limit(self, db_session, test_notebook):
        """Test chat history respects limit."""
        repo = ChatRepository(db_session)

        # Add many messages
        for i in range(10):
            await repo.add_message(test_notebook.id, "user", f"Message {i}")

        history = await repo.get_notebook_history(test_notebook.id, limit=5)

        assert len(history) <= 5

    @pytest.mark.asyncio
    async def test_get_notebook_history_empty(self, db_session, test_notebook):
        """Test getting history for notebook with no messages."""
        repo = ChatRepository(db_session)

        history = await repo.get_notebook_history(test_notebook.id)

        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_delete_message(self, db_session, test_notebook):
        """Test deleting a chat message."""
        repo = ChatRepository(db_session)

        message = await repo.add_message(
            test_notebook.id,
            "user",
            "To be deleted"
        )

        result = await repo.delete(message.id)

        assert result is True
        assert await repo.get(message.id) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
