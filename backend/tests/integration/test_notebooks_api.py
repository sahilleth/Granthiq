"""
Integration tests for Notebooks API endpoints.

Tests the complete notebook lifecycle including:
- Creating notebooks
- Listing notebooks
- Updating notebooks
- Deleting notebooks
- Notebook settings management
"""

import sys
from pathlib import Path

# Add backend directory to path for direct execution
_backend_dir = Path(__file__).parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import pytest
from uuid import uuid4
from httpx import AsyncClient

from src.db.repositories.notebook import NotebookRepository


class TestNotebookCreation:
    """Test notebook creation endpoints."""

    @pytest.mark.asyncio
    async def test_create_notebook_success(self, client: AsyncClient):
        """Test successful notebook creation."""
        response = await client.post(
            "/api/v1/notebooks",
            json={"title": "Test Notebook"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Notebook"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_create_notebook_with_default_title(self, client: AsyncClient):
        """Test notebook creation with default title."""
        response = await client.post(
            "/api/v1/notebooks",
            json={}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Untitled Notebook"

    @pytest.mark.asyncio
    async def test_create_notebook_with_custom_settings(self, client: AsyncClient):
        """Test notebook creation with custom RAG settings."""
        custom_settings = {
            "use_hyde": True,
            "top_k_results": 15,
            "chunking_strategy": "semantic"
        }

        response = await client.post(
            "/api/v1/notebooks",
            json={"title": "Custom Settings Notebook", "settings": custom_settings}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["settings"]["use_hyde"] is True
        assert data["settings"]["top_k_results"] == 15

    @pytest.mark.asyncio
    async def test_create_notebook_with_long_title(self, client: AsyncClient):
        """Test notebook creation with long title."""
        long_title = "A" * 500
        response = await client.post(
            "/api/v1/notebooks",
            json={"title": long_title}
        )

        # Should succeed or return validation error depending on limits
        assert response.status_code in [201, 422]


class TestNotebookRetrieval:
    """Test notebook retrieval endpoints."""

    @pytest.mark.asyncio
    async def test_list_notebooks_empty(self, client: AsyncClient):
        """Test listing notebooks when user has none."""
        response = await client.get("/api/v1/notebooks")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_notebooks_with_data(self, client: AsyncClient):
        """Test listing notebooks after creating some."""
        # Create notebooks
        await client.post("/api/v1/notebooks", json={"title": "Notebook 1"})
        await client.post("/api/v1/notebooks", json={"title": "Notebook 2"})
        await client.post("/api/v1/notebooks", json={"title": "Notebook 3"})

        response = await client.get("/api/v1/notebooks")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3

    @pytest.mark.asyncio
    async def test_get_notebook_by_id(self, client: AsyncClient):
        """Test retrieving a specific notebook by ID."""
        # Create notebook
        create_response = await client.post(
            "/api/v1/notebooks",
            json={"title": "Test Get"}
        )
        notebook_id = create_response.json()["id"]

        # Retrieve notebook
        response = await client.get(f"/api/v1/notebooks/{notebook_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == notebook_id
        assert data["title"] == "Test Get"

    @pytest.mark.asyncio
    async def test_get_nonexistent_notebook(self, client: AsyncClient):
        """Test retrieving a notebook that doesn't exist."""
        fake_id = str(uuid4())
        response = await client.get(f"/api/v1/notebooks/{fake_id}")

        assert response.status_code == 404
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_get_notebook_invalid_uuid(self, client: AsyncClient):
        """Test retrieving with invalid UUID format."""
        response = await client.get("/api/v1/notebooks/invalid-uuid")

        assert response.status_code == 422


class TestNotebookUpdate:
    """Test notebook update endpoints."""

    @pytest.mark.asyncio
    async def test_update_notebook_title(self, client: AsyncClient):
        """Test updating notebook title."""
        # Create notebook
        create_response = await client.post(
            "/api/v1/notebooks",
            json={"title": "Original Title"}
        )
        notebook_id = create_response.json()["id"]

        # Update notebook
        response = await client.patch(
            f"/api/v1/notebooks/{notebook_id}",
            json={"title": "Updated Title"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_notebook_settings(self, client: AsyncClient):
        """Test updating notebook RAG settings."""
        # Create notebook
        create_response = await client.post(
            "/api/v1/notebooks",
            json={"title": "Settings Test"}
        )
        notebook_id = create_response.json()["id"]

        # Update settings
        new_settings = {
            "use_hyde": True,
            "top_k_results": 20,
            "enable_reranking": True
        }
        response = await client.patch(
            f"/api/v1/notebooks/{notebook_id}",
            json={"settings": new_settings}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["use_hyde"] is True
        assert data["settings"]["top_k_results"] == 20

    @pytest.mark.asyncio
    async def test_update_nonexistent_notebook(self, client: AsyncClient):
        """Test updating a notebook that doesn't exist."""
        fake_id = str(uuid4())
        response = await client.patch(
            f"/api/v1/notebooks/{fake_id}",
            json={"title": "New Title"}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_partial_update_preserves_other_fields(self, client: AsyncClient):
        """Test that partial update doesn't clear other fields."""
        # Create notebook with settings
        create_response = await client.post(
            "/api/v1/notebooks",
            json={
                "title": "Original",
                "settings": {"use_hyde": True, "top_k_results": 10}
            }
        )
        notebook_id = create_response.json()["id"]

        # Update only title
        response = await client.patch(
            f"/api/v1/notebooks/{notebook_id}",
            json={"title": "New Title"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Title"
        # Settings should be preserved
        assert data["settings"]["use_hyde"] is True


class TestNotebookDeletion:
    """Test notebook deletion endpoints."""

    @pytest.mark.asyncio
    async def test_delete_notebook_success(self, client: AsyncClient):
        """Test successful notebook deletion."""
        # Create notebook
        create_response = await client.post(
            "/api/v1/notebooks",
            json={"title": "To Delete"}
        )
        notebook_id = create_response.json()["id"]

        # Delete notebook
        response = await client.delete(f"/api/v1/notebooks/{notebook_id}")

        assert response.status_code == 204

        # Verify deletion
        get_response = await client.get(f"/api/v1/notebooks/{notebook_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_notebook(self, client: AsyncClient):
        """Test deleting a notebook that doesn't exist."""
        fake_id = str(uuid4())
        response = await client.delete(f"/api/v1/notebooks/{fake_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_notebook_with_documents(self, client: AsyncClient, test_document):
        """Test deleting a notebook that has documents."""
        # The test_document fixture creates a document in test_notebook
        # Deleting the notebook should cascade delete documents
        notebook_id = test_document.notebook_id

        response = await client.delete(f"/api/v1/notebooks/{notebook_id}")

        # Should succeed (cascade delete)
        assert response.status_code in [204, 404]  # 404 if already deleted by other tests


class TestNotebookListOrdering:
    """Test notebook listing order and pagination."""

    @pytest.mark.asyncio
    async def test_notebooks_ordered_by_updated(self, client: AsyncClient):
        """Test that notebooks are returned ordered by updated_at descending."""
        # Create notebooks
        await client.post("/api/v1/notebooks", json={"title": "First"})
        await client.post("/api/v1/notebooks", json={"title": "Second"})
        create_response = await client.post("/api/v1/notebooks", json={"title": "Third"})
        third_id = create_response.json()["id"]

        # Get list
        response = await client.get("/api/v1/notebooks")
        data = response.json()

        # Most recently created should be first
        assert data[0]["id"] == third_id


class TestNotebookValidation:
    """Test notebook input validation."""

    @pytest.mark.asyncio
    async def test_empty_settings_object(self, client: AsyncClient):
        """Test creating notebook with empty settings object."""
        response = await client.post(
            "/api/v1/notebooks",
            json={"title": "Test", "settings": {}}
        )

        assert response.status_code == 201
        assert response.json()["settings"] == {}

    @pytest.mark.asyncio
    async def test_invalid_settings_type(self, client: AsyncClient):
        """Test creating notebook with invalid settings type."""
        response = await client.post(
            "/api/v1/notebooks",
            json={"title": "Test", "settings": "not an object"}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_extra_fields_ignored(self, client: AsyncClient):
        """Test that extra fields in request are ignored."""
        response = await client.post(
            "/api/v1/notebooks",
            json={
                "title": "Test",
                "extra_field": "should be ignored",
                "another_extra": 123
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert "extra_field" not in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
