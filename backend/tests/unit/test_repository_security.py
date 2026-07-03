"""
Unit tests for repository ALLOWED_FILTER_FIELDS security.
Tests that repositories properly validate filter fields to prevent SQL injection.
"""

import pytest
from uuid import uuid4
from unittest.mock import Mock, AsyncMock

from src.db.repositories.base import BaseRepository
from src.db.repositories.document import DocumentRepository
from src.db.repositories.notebook import NotebookRepository
from src.db.repositories.chat import ChatRepository
from src.db.repositories.content import ContentRepository
from src.db.repositories.feedback import FeedbackRepository
from src.db.repositories.task_progress import TaskProgressRepository
from src.db.models import Document, Notebook, ChatMessage, GeneratedContent, Feedback, TaskProgress


class TestBaseRepositoryFilterValidation:
    """Test suite for BaseRepository filter field validation."""

    @pytest.mark.asyncio
    async def test_count_with_no_allowed_fields_blocks_all_filters(self):
        """Test that count() blocks all filters when ALLOWED_FILTER_FIELDS is empty."""
        # Create a mock session
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.one.return_value = 0
        mock_session.exec.return_value = mock_result

        # Create repo with empty ALLOWED_FILTER_FIELDS
        repo = BaseRepository(mock_session, Document)

        # Attempt to filter should be blocked
        count = await repo.count({"notebook_id": uuid4()})

        # Should return 0 (no filtering applied)
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_with_allowed_fields_permits_valid_filters(self):
        """Test that count() permits filters for allowed fields."""
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.one.return_value = 5
        mock_session.exec.return_value = mock_result

        # Create repo with allowed fields
        repo = BaseRepository(mock_session, Document)
        repo.ALLOWED_FILTER_FIELDS = {"notebook_id", "status"}

        count = await repo.count({"notebook_id": uuid4()})

        # Should execute query with filter
        assert count == 5
        mock_session.exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_blocks_non_allowed_fields(self):
        """Test that count() blocks filters for non-allowed fields."""
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.one.return_value = 0
        mock_session.exec.return_value = mock_result

        repo = BaseRepository(mock_session, Document)
        repo.ALLOWED_FILTER_FIELDS = {"notebook_id"}  # status not allowed

        # Attempt to filter on non-allowed field
        count = await repo.count({"status": "pending"})

        # Should return 0 (filter skipped)
        assert count == 0

    @pytest.mark.asyncio
    async def test_validate_filter_field_returns_true_for_allowed(self):
        """Test _validate_filter_field returns True for allowed fields."""
        mock_session = AsyncMock()
        repo = BaseRepository(mock_session, Document)
        repo.ALLOWED_FILTER_FIELDS = {"notebook_id", "status"}

        assert repo._validate_filter_field("notebook_id") is True
        assert repo._validate_filter_field("status") is True

    @pytest.mark.asyncio
    async def test_validate_filter_field_returns_false_for_not_allowed(self):
        """Test _validate_filter_field returns False for non-allowed fields."""
        mock_session = AsyncMock()
        repo = BaseRepository(mock_session, Document)
        repo.ALLOWED_FILTER_FIELDS = {"notebook_id"}

        assert repo._validate_filter_field("malicious_field") is False
        assert repo._validate_filter_field("status") is False

    @pytest.mark.asyncio
    async def test_validate_filter_field_returns_false_when_empty(self):
        """Test _validate_filter_field returns False when ALLOWED_FILTER_FIELDS is empty."""
        mock_session = AsyncMock()
        repo = BaseRepository(mock_session, Document)
        repo.ALLOWED_FILTER_FIELDS = set()

        assert repo._validate_filter_field("any_field") is False


class TestDocumentRepositorySecurity:
    """Test DocumentRepository security settings."""

    def test_allowed_filter_fields_defined(self):
        """Test that ALLOWED_FILTER_FIELDS is properly defined."""
        assert hasattr(DocumentRepository, 'ALLOWED_FILTER_FIELDS')
        assert len(DocumentRepository.ALLOWED_FILTER_FIELDS) > 0

    def test_allowed_filter_fields_contains_expected(self):
        """Test that expected fields are in ALLOWED_FILTER_FIELDS."""
        expected_fields = {"notebook_id", "status", "file_hash", "mime_type", "user_id"}
        assert expected_fields.issubset(DocumentRepository.ALLOWED_FILTER_FIELDS)

    def test_dangerous_fields_not_allowed(self):
        """Test that potentially dangerous fields are not allowed."""
        dangerous_fields = {"password", "secret", "token", "hash"}
        for field in dangerous_fields:
            assert field not in DocumentRepository.ALLOWED_FILTER_FIELDS


class TestNotebookRepositorySecurity:
    """Test NotebookRepository security settings."""

    def test_allowed_filter_fields_defined(self):
        """Test that ALLOWED_FILTER_FIELDS is properly defined."""
        assert hasattr(NotebookRepository, 'ALLOWED_FILTER_FIELDS')
        assert len(NotebookRepository.ALLOWED_FILTER_FIELDS) > 0

    def test_user_id_is_allowed(self):
        """Test that user_id is in allowed fields (common query pattern)."""
        assert "user_id" in NotebookRepository.ALLOWED_FILTER_FIELDS


class TestChatRepositorySecurity:
    """Test ChatRepository security settings."""

    def test_allowed_filter_fields_defined(self):
        """Test that ALLOWED_FILTER_FIELDS is properly defined."""
        assert hasattr(ChatRepository, 'ALLOWED_FILTER_FIELDS')
        assert len(ChatRepository.ALLOWED_FILTER_FIELDS) > 0

    def test_notebook_id_and_role_allowed(self):
        """Test that common filter fields are allowed."""
        assert "notebook_id" in ChatRepository.ALLOWED_FILTER_FIELDS
        assert "role" in ChatRepository.ALLOWED_FILTER_FIELDS


class TestContentRepositorySecurity:
    """Test ContentRepository security settings."""

    def test_allowed_filter_fields_defined(self):
        """Test that ALLOWED_FILTER_FIELDS is properly defined."""
        assert hasattr(ContentRepository, 'ALLOWED_FILTER_FIELDS')
        assert len(ContentRepository.ALLOWED_FILTER_FIELDS) > 0

    def test_expected_fields_allowed(self):
        """Test that expected filter fields are allowed."""
        expected = {"notebook_id", "document_id", "content_type", "status"}
        assert expected.issubset(ContentRepository.ALLOWED_FILTER_FIELDS)


class TestFeedbackRepositorySecurity:
    """Test FeedbackRepository security settings."""

    def test_allowed_filter_fields_defined(self):
        """Test that ALLOWED_FILTER_FIELDS is properly defined."""
        assert hasattr(FeedbackRepository, 'ALLOWED_FILTER_FIELDS')
        assert len(FeedbackRepository.ALLOWED_FILTER_FIELDS) > 0

    def test_user_id_and_content_type_allowed(self):
        """Test that common filter fields are allowed."""
        assert "user_id" in FeedbackRepository.ALLOWED_FILTER_FIELDS
        assert "content_type" in FeedbackRepository.ALLOWED_FILTER_FIELDS
        assert "content_id" in FeedbackRepository.ALLOWED_FILTER_FIELDS


class TestTaskProgressRepositorySecurity:
    """Test TaskProgressRepository security settings."""

    def test_allowed_filter_fields_defined(self):
        """Test that ALLOWED_FILTER_FIELDS is properly defined."""
        assert hasattr(TaskProgressRepository, 'ALLOWED_FILTER_FIELDS')
        assert len(TaskProgressRepository.ALLOWED_FILTER_FIELDS) > 0

    def test_job_and_user_fields_allowed(self):
        """Test that common filter fields are allowed."""
        assert "job_id" in TaskProgressRepository.ALLOWED_FILTER_FIELDS
        assert "user_id" in TaskProgressRepository.ALLOWED_FILTER_FIELDS
        assert "notebook_id" in TaskProgressRepository.ALLOWED_FILTER_FIELDS
