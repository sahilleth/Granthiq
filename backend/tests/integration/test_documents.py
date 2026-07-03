"""
Tests for document endpoints.
"""
import sys
from pathlib import Path

# Add backend directory to path for direct execution
_backend_dir = Path(__file__).parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import pytest
import uuid
import io
from httpx import AsyncClient
from src.db.repositories.document import DocumentRepository
from src.db.repositories.notebook import NotebookRepository
from src.db.models import Document, ProcessingStatus


@pytest.mark.asyncio
async def test_upload_document(client: AsyncClient, test_notebook, sample_pdf_content):
    """Test uploading a document successfully."""
    files = {
        "file": ("Clinical.pdf", io.BytesIO(sample_pdf_content), "application/pdf")
    }
    data = {
        "notebook_id": str(test_notebook.id)
    }
    
    response = await client.post(
        "/api/v1/documents/upload",
        files=files,
        data=data
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "uploaded"
    assert "document_id" in result
    assert result["filename"] == "Clinical.pdf"
    assert result["processing_status"] == ProcessingStatus.PENDING.value


@pytest.mark.asyncio
async def test_upload_document_invalid_notebook(client: AsyncClient, sample_pdf_content):
    """Test that uploading to non-existent notebook returns 403."""
    fake_notebook_id = uuid.uuid4()
    files = {
        "file": ("Clinical.pdf", io.BytesIO(sample_pdf_content), "application/pdf")
    }
    data = {
        "notebook_id": str(fake_notebook_id)
    }
    
    response = await client.post(
        "/api/v1/documents/upload",
        files=files,
        data=data
    )
    assert response.status_code == 403
    assert "not found" in response.json()["detail"].lower() or "access denied" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_document_text_file(client: AsyncClient, test_notebook, sample_text_content):
    """Test uploading a text file."""
    files = {
        "file": ("test.txt", io.BytesIO(sample_text_content), "text/plain")
    }
    data = {
        "notebook_id": str(test_notebook.id)
    }
    
    response = await client.post(
        "/api/v1/documents/upload",
        files=files,
        data=data
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "uploaded"
    assert result["filename"] == "test.txt"


@pytest.mark.asyncio
async def test_get_document_url(client: AsyncClient, test_document):
    """Test getting a signed URL for a document."""
    response = await client.get(f"/api/v1/documents/{test_document.id}/url")
    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert "expires_in" in data
    assert data["expires_in"] == 3600  # 1 hour
    assert data["url"].startswith("http")


@pytest.mark.asyncio
async def test_get_document_url_not_found(client: AsyncClient):
    """Test that getting URL for non-existent document returns 404."""
    fake_id = uuid.uuid4()
    response = await client.get(f"/api/v1/documents/{fake_id}/url")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient, test_notebook, test_document):
    """Test listing all documents in a notebook."""
    response = await client.get(f"/api/v1/documents/notebook/{test_notebook.id}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    doc_ids = [doc["id"] for doc in data]
    assert str(test_document.id) in doc_ids


@pytest.mark.asyncio
async def test_list_documents_empty(client: AsyncClient, test_user, db_session):
    """Test listing documents for notebook with no documents."""
    # Create a new notebook without documents
    repo = NotebookRepository(db_session)
    notebook = await repo.create_notebook(test_user.id, "Empty Notebook")
    
    response = await client.get(f"/api/v1/documents/notebook/{notebook.id}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_list_documents_unauthorized(client: AsyncClient, other_user_id, db_session):
    """Test that listing documents for another user's notebook returns 404."""
    # Create notebook for other user
    repo = NotebookRepository(db_session)
    notebook = await repo.create_notebook(other_user_id, "Other User's Notebook")
    
    # Try to access it as test_user (via dependency override)
    response = await client.get(f"/api/v1/documents/notebook/{notebook.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient, test_notebook, db_session):
    """Test deleting a document."""
    # Create a document to delete
    doc_repo = DocumentRepository(db_session)
    doc = Document(
        notebook_id=test_notebook.id,
        filename="to_delete.pdf",
        file_path=f"test/{test_notebook.id}/to_delete.pdf",
        mime_type="application/pdf",
        status=ProcessingStatus.COMPLETED
    )
    saved_doc = await doc_repo.create(doc)
    
    response = await client.delete(f"/api/v1/documents/{saved_doc.id}")
    assert response.status_code == 204
    
    # Verify it's deleted
    deleted_doc = await doc_repo.get(saved_doc.id)
    assert deleted_doc is None


@pytest.mark.asyncio
async def test_delete_document_not_found(client: AsyncClient):
    """Test that deleting non-existent document returns 404."""
    fake_id = uuid.uuid4()
    response = await client.delete(f"/api/v1/documents/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_unauthorized(client: AsyncClient, other_user_id, db_session):
    """Test that deleting another user's document returns 403."""
    # Create notebook and document for other user
    notebook_repo = NotebookRepository(db_session)
    notebook = await notebook_repo.create_notebook(other_user_id, "Other User's Notebook")
    
    doc_repo = DocumentRepository(db_session)
    doc = Document(
        notebook_id=notebook.id,
        filename="other_user.pdf",
        file_path=f"test/{notebook.id}/other_user.pdf",
        mime_type="application/pdf"
    )
    saved_doc = await doc_repo.create(doc)
    
    # Try to delete it as test_user
    response = await client.delete(f"/api/v1/documents/{saved_doc.id}")
    assert response.status_code == 403


if __name__ == "__main__":
    import asyncio
    import io
    
    async def run_tests():
        from httpx import AsyncClient
        from src.app import create_app
        from src.services.auth import get_current_user
        from src.db.session import get_session, async_session_factory
        from tests.conftest import TEST_USER_ID, ensure_test_user_exists
        from tests.fixtures.test_data import create_sample_pdf
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
        
        # Create notebook (user already exists)
        async with async_session_factory() as session:
            notebook_repo = NotebookRepository(session)
            notebook = await notebook_repo.create_notebook(TEST_USER_ID, "Test Notebook")
            notebook_id = notebook.id
        
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            print("Running test_upload_document...")
            pdf_content = create_sample_pdf()
            files = {
                "file": ("Clinical.pdf", io.BytesIO(pdf_content), "application/pdf")
            }
            data = {"notebook_id": str(notebook_id)}
            response = await client.post(
                "/api/v1/documents/upload",
                files=files,
                data=data
            )
            print(f"Status: {response.status_code}")
            assert response.status_code == 200
            doc_id = response.json()["document_id"]
            
            print("\nRunning test_get_document_url...")
            response = await client.get(f"/api/v1/documents/{doc_id}/url")
            print(f"Status: {response.status_code}")
            assert response.status_code == 200
            
            print("\nRunning test_list_documents...")
            response = await client.get(f"/api/v1/documents/notebook/{notebook_id}")
            print(f"Status: {response.status_code}, Count: {len(response.json())}")
            assert response.status_code == 200
            
        app.dependency_overrides.clear()
        print("\n✅ Document tests passed!")
    
    asyncio.run(run_tests())
