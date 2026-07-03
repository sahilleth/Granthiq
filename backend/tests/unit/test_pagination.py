"""
Tests for cursor-based pagination functionality.
"""

import pytest
from uuid import uuid4
from src.schemas.pagination import (
    CursorPage,
    PaginationParams,
    encode_cursor,
    decode_cursor,
    build_pagination_response,
)
from src.db.models import Notebook, Document, ChatMessage, ChatRole
from src.db.repositories.notebook import NotebookRepository
from src.db.repositories.document import DocumentRepository
from src.db.repositories.chat import ChatRepository


class TestCursorPagination:
    """Tests for cursor pagination encoding/decoding."""

    def test_encode_decode_cursor_roundtrip(self):
        """Test that encoding and decoding returns original values."""
        item_id = "test-item-id-123"
        cursor = encode_cursor(item_id)

        decoded = decode_cursor(cursor)
        assert decoded == item_id

    def test_encode_cursor_deterministic(self):
        """Test that encoding the same ID produces the same cursor."""
        item_id = "test-item-id-456"
        cursor1 = encode_cursor(item_id)
        cursor2 = encode_cursor(item_id)

        assert cursor1 == cursor2

    def test_decode_cursor_invalid_returns_none(self):
        """Test that invalid cursor returns None."""
        assert decode_cursor("invalid-cursor") is None
        assert decode_cursor("") is None
        assert decode_cursor(None) is None

    def test_build_pagination_response_empty(self):
        """Test pagination response with empty results."""
        response = build_pagination_response(
            items=[],
            page_params=PaginationParams(limit=10),
            item_count=0,
        )

        assert response.items == []
        assert response.next_cursor is None
        assert response.has_more is False
        assert response.total == 0

    def test_build_pagination_response_single_page(self):
        """Test pagination response when results fit in one page."""
        items = [{"id": "1"}, {"id": "2"}, {"id": "3"}]

        response = build_pagination_response(
            items=items,
            page_params=PaginationParams(limit=10),
            item_count=3,
        )

        assert len(response.items) == 3
        assert response.next_cursor is None
        assert response.has_more is False
        assert response.total == 3

    def test_build_pagination_response_has_more(self):
        """Test pagination response when there are more results."""
        items = [{"id": str(i)} for i in range(10)]

        response = build_pagination_response(
            items=items,
            page_params=PaginationParams(limit=10),
            item_count=25,
        )

        assert len(response.items) == 10
        assert response.next_cursor is not None
        assert response.has_more is True
        assert response.total == 25


@pytest.mark.asyncio
class TestNotebookPagination:
    """Tests for notebook list endpoint pagination."""

    async def test_list_notebooks_pagination(self, client, test_user, db_session):
        """Test that notebooks are paginated correctly."""
        repo = NotebookRepository(db_session)

        # Create multiple notebooks
        for i in range(5):
            await repo.create_notebook(test_user.id, f"Test Notebook {i}")

        # First page
        response = await client.get("/api/v1/notebooks?limit=2")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 2
        assert data["has_more"] is True

    async def test_list_notebooks_with_cursor(self, client, test_user, db_session):
        """Test pagination with cursor."""
        repo = NotebookRepository(db_session)

        # Create notebooks
        for i in range(5):
            await repo.create_notebook(test_user.id, f"Cursor Test {i}")

        # Get first page
        response = await client.get("/api/v1/notebooks?limit=2")
        first_page = response.json()

        # Get second page using cursor
        if first_page.get("next_cursor"):
            response = await client.get(
                f"/api/v1/notebooks?limit=2&cursor={first_page['next_cursor']}"
            )
            second_page = response.json()

            # Verify no duplicates
            first_ids = {item["id"] for item in first_page["items"]}
            second_ids = {item["id"] for item in second_page["items"]}
            assert first_ids.isdisjoint(second_ids)


@pytest.mark.asyncio
class TestDocumentPagination:
    """Tests for document list endpoint pagination."""

    async def test_list_documents_pagination(
        self, client, test_user, test_notebook, db_session
    ):
        """Test that documents are paginated correctly."""
        doc_repo = DocumentRepository(db_session)

        # Create multiple documents
        for i in range(5):
            from src.db.models import Document, ProcessingStatus

            doc = Document(
                notebook_id=test_notebook.id,
                filename=f"test{i}.pdf",
                file_path=f"test{i}.pdf",
                mime_type="application/pdf",
                status=ProcessingStatus.COMPLETED,
                chunk_count=1,
            )
            await doc_repo.create(doc)

        response = await client.get(
            f"/api/v1/notebooks/{test_notebook.id}/documents?limit=2"
        )
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 2
        assert data["has_more"] is True


@pytest.mark.asyncio
class TestChatHistoryPagination:
    """Tests for chat history pagination."""

    async def test_get_history_pagination(
        self, client, test_user, test_notebook, db_session
    ):
        """Test that chat history is paginated correctly."""
        chat_repo = ChatRepository(db_session)

        # Create multiple chat messages
        for i in range(10):
            await chat_repo.add_message(
                notebook_id=test_notebook.id,
                role=ChatRole.USER if i % 2 == 0 else ChatRole.ASSISTANT,
                content=f"Test message {i}",
            )

        # Get first page
        response = await client.get(f"/api/v1/chat/{test_notebook.id}/history?limit=3")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 3
        assert data["has_more"] is True

    async def test_get_history_count(
        self, client, test_user, test_notebook, db_session
    ):
        """Test that history count is returned."""
        chat_repo = ChatRepository(db_session)

        # Create messages
        for i in range(5):
            await chat_repo.add_message(
                notebook_id=test_notebook.id,
                role=ChatRole.USER,
                content=f"Message {i}",
            )

        response = await client.get(f"/api/v1/chat/{test_notebook.id}/history?limit=10")
        assert response.status_code == 200

        data = response.json()
        assert "total" in data
        assert data["total"] >= 5
