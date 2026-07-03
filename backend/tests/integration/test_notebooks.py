"""
Tests for notebook endpoints.
"""
import sys
from pathlib import Path

# Add backend directory to path for direct execution
_backend_dir = Path(__file__).parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import pytest
import uuid
from httpx import AsyncClient
from src.db.repositories.notebook import NotebookRepository
from src.db.repositories.document import DocumentRepository
from src.db.models import Document, ChatMessage


@pytest.mark.asyncio
async def test_list_notebooks_empty(client: AsyncClient, test_user, db_session):
    """Test that new user has empty notebook list."""
    response = await client.get("/api/v1/notebooks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_create_notebook(client: AsyncClient, test_user_id):
    """Test creating a notebook successfully."""
    response = await client.post(
        "/api/v1/notebooks",
        json={"title": "Test Notebook"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Notebook"
    assert data["user_id"] == str(test_user_id)
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_notebook_with_settings(client: AsyncClient, test_user_id):
    """Test creating a notebook with RAG settings."""
    settings = {
        "use_hyde": True,
        "default_alpha": 0.7,
        "top_k_results": 10,
        "enable_reranking": True
    }
    response = await client.post(
        "/api/v1/notebooks",
        json={
            "title": "Notebook with Settings",
            "settings": settings
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Notebook with Settings"
    assert data["user_id"] == str(test_user_id)
    assert "settings" in data
    assert data["settings"]["use_hyde"] is True
    assert data["settings"]["default_alpha"] == 0.7


@pytest.mark.asyncio
async def test_get_notebook(client: AsyncClient, test_notebook):
    """Test getting a notebook by ID."""
    response = await client.get(f"/api/v1/notebooks/{test_notebook.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_notebook.id)
    assert data["title"] == test_notebook.title
    assert data["user_id"] == str(test_notebook.user_id)


@pytest.mark.asyncio
async def test_get_notebook_not_found(client: AsyncClient):
    """Test that getting non-existent notebook returns 404."""
    fake_id = uuid.uuid4()
    response = await client.get(f"/api/v1/notebooks/{fake_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_notebooks_with_data(client: AsyncClient, test_notebook):
    """Test listing notebooks returns created notebooks."""
    response = await client.get("/api/v1/notebooks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    notebook_ids = [nb["id"] for nb in data]
    assert str(test_notebook.id) in notebook_ids


@pytest.mark.asyncio
async def test_update_notebook_title(client: AsyncClient, test_notebook):
    """Test updating notebook title."""
    new_title = "Updated Notebook Title"
    response = await client.patch(
        f"/api/v1/notebooks/{test_notebook.id}",
        json={"title": new_title}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == new_title
    assert data["id"] == str(test_notebook.id)


@pytest.mark.asyncio
async def test_update_notebook_settings(client: AsyncClient, test_notebook):
    """Test updating notebook settings."""
    new_settings = {
        "use_hyde": False,
        "default_alpha": 0.5,
        "top_k_results": 5
    }
    response = await client.patch(
        f"/api/v1/notebooks/{test_notebook.id}",
        json={"settings": new_settings}
    )
    assert response.status_code == 200
    data = response.json()
    assert "settings" in data
    assert data["settings"]["use_hyde"] is False
    assert data["settings"]["default_alpha"] == 0.5
    assert data["settings"]["top_k_results"] == 5


@pytest.mark.asyncio
async def test_update_notebook_title_and_settings(client: AsyncClient, test_notebook):
    """Test updating both title and settings at once."""
    new_title = "Updated Title and Settings"
    new_settings = {
        "enable_reranking": True,
        "reranker_top_n": 3
    }
    response = await client.patch(
        f"/api/v1/notebooks/{test_notebook.id}",
        json={
            "title": new_title,
            "settings": new_settings
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == new_title
    assert data["settings"]["enable_reranking"] is True
    assert data["settings"]["reranker_top_n"] == 3


@pytest.mark.asyncio
async def test_delete_notebook(client: AsyncClient, test_user, db_session):
    """Test deleting a notebook."""
    # Create a notebook to delete
    repo = NotebookRepository(db_session)
    notebook = await repo.create_notebook(test_user.id, "To Be Deleted")
    
    response = await client.delete(f"/api/v1/notebooks/{notebook.id}")
    assert response.status_code == 204
    
    # Verify it's deleted
    response = await client.get(f"/api/v1/notebooks/{notebook.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_notebook_cascade(client: AsyncClient, test_user, db_session):
    """Test that deleting notebook cascades to related data."""
    # Create notebook with document and chat message
    repo = NotebookRepository(db_session)
    notebook = await repo.create_notebook(test_user.id, "Cascade Test")
    
    doc_repo = DocumentRepository(db_session)
    doc = Document(
        notebook_id=notebook.id,
        filename="test.pdf",
        file_path=f"test/{notebook.id}/test.pdf",
        mime_type="application/pdf"
    )
    await doc_repo.create(doc)
    
    from src.db.models import ChatMessage
    chat_msg = ChatMessage(
        notebook_id=notebook.id,
        role="user",
        content="Test message"
    )
    db_session.add(chat_msg)
    await db_session.commit()
    
    # Delete notebook
    response = await client.delete(f"/api/v1/notebooks/{notebook.id}")
    assert response.status_code == 204
    
    # Verify document is deleted (cascade)
    deleted_doc = await doc_repo.get(doc.id)
    assert deleted_doc is None
    
    # Verify chat message is deleted (cascade)
    from sqlmodel import select
    result = await db_session.exec(select(ChatMessage).where(ChatMessage.id == chat_msg.id))
    assert result.first() is None


@pytest.mark.asyncio
async def test_delete_notebook_not_found(client: AsyncClient):
    """Test deleting non-existent notebook returns 404."""
    fake_id = uuid.uuid4()
    response = await client.delete(f"/api/v1/notebooks/{fake_id}")
    assert response.status_code == 404


if __name__ == "__main__":
    import asyncio
    
    async def run_tests():
        from httpx import AsyncClient
        from src.app import create_app
        from src.services.auth import get_current_user
        from src.db.session import get_session, async_session_factory
        from tests.conftest import TEST_USER_ID, ensure_test_user_exists
        from src.db.repositories.notebook import NotebookRepository
        
        # Ensure test user exists first
        async with async_session_factory() as session:
            await ensure_test_user_exists(session)
        
        # Setup app with overrides
        app = create_app()
        
        async def override_get_current_user():
            return TEST_USER_ID
        
        async def override_get_session():
            async with async_session_factory() as session:
                yield session
        
        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_session] = override_get_session
        
        from httpx import ASGITransport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            print("Running test_list_notebooks_empty...")
            response = await client.get("/api/v1/notebooks")
            print(f"Status: {response.status_code}, Count: {len(response.json())}")
            assert response.status_code == 200
            
            print("\nRunning test_create_notebook...")
            response = await client.post(
                "/api/v1/notebooks",
                json={"title": "Test Notebook"}
            )
            print(f"Status: {response.status_code}")
            assert response.status_code == 201
            notebook_id = response.json()["id"]
            
            print("\nRunning test_get_notebook...")
            response = await client.get(f"/api/v1/notebooks/{notebook_id}")
            print(f"Status: {response.status_code}")
            assert response.status_code == 200
            
        app.dependency_overrides.clear()
        print("\n✅ Notebook tests passed!")
    
    asyncio.run(run_tests())
