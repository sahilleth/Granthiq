"""
Integration tests for Task Queue processing.
Tests the complete production flow: API -> Queue -> Database -> Status Tracking
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import io
import asyncio
import uuid
from httpx import AsyncClient
from sqlmodel import select, text

from src.db.models import ProcessingStatus, Document, GeneratedContent, ContentType
from src.db.repositories.task_progress import TaskProgressRepository
from src.services.queue.app import proc_app

pytest_plugins = ("pytest_asyncio",)
from src.services.queue.tasks import process_document_task, generate_podcast_task

@pytest.fixture
def mock_storage_service():
    """Mock storage service to avoid real file operations."""
    with patch("src.routers.documents.get_storage_service") as mock_get_storage:
        mock_storage = AsyncMock()
        mock_get_storage.return_value = mock_storage
        # Mock successful upload
        mock_storage.upload_stream.return_value = None
        # Mock successful download URL generation
        mock_storage.get_url.return_value = "https://fake-storage.com/test-file.pdf"
        yield mock_storage

@pytest.fixture
async def open_proc_app():
    """
    Ensure proc_app is open during tests. 
    This mimics what the app lifespan SHOULD do (if we fix it) or what verifying the bug requires.
    """
    async with proc_app.open_async():
        yield proc_app

@pytest.mark.asyncio
async def test_upload_enqueues_job_real_queue(
    client: AsyncClient, 
    test_notebook, 
    sample_pdf_content,
    mock_storage_service,
    db_session,
    open_proc_app # This ensures connection pool is ready
):
    """
    PRODUCTION FLOW TEST (REAL QUEUE):
    1. Upload document with USE_TASK_QUEUE=True
    2. Let Procrastinate actually insert into DB
    3. Verify job exists in procrastinate_jobs table
    """
    # Force strict usage of Task Queue
    with patch("src.routers.documents.USE_TASK_QUEUE", True):
        
        files = {
            "file": ("real_queue_test.pdf", io.BytesIO(sample_pdf_content), "application/pdf")
        }
        data = {"notebook_id": str(test_notebook.id)}
        
        # This calling the real router, which calls real process_document_task.defer_async
        response = await client.post(
            "/api/v1/documents/upload",
            files=files,
            data=data
        )
        
        # Assertions
        assert response.status_code == 200
        result = response.json()
        
        # 1. Verify Response
        task_id = result.get("task_id")
        assert task_id is not None, "Real queue should return a valid integer task_id"
        assert isinstance(task_id, int)
        
        # 2. Verify Document in DB
        doc = await db_session.get(Document, result["document_id"])
        assert doc is not None
        assert doc.status == ProcessingStatus.PENDING
        
        # 3. Verify Job in Procrastinate DB Table (The "Real" Check)
        # We use raw SQL to check the procrastinate_jobs table
        query = text("SELECT id, status, task_name FROM procrastinate_jobs WHERE id = :id")
        job_row = (await db_session.exec(query.bindparams(id=task_id))).first()
        
        assert job_row is not None
        assert job_row.id == task_id
        assert job_row.status == "todo"
        assert job_row.task_name == "src.services.queue.tasks.process_document_task"

@pytest.mark.asyncio
async def test_upload_fallback_when_queue_disabled(
    client: AsyncClient, 
    test_notebook, 
    sample_pdf_content,
    mock_storage_service,
    db_session
):
    """
    Test that when USE_TASK_QUEUE=False, we fall back to BackgroundTasks.
    """
    with patch("src.routers.documents.USE_TASK_QUEUE", False):
        files = {
            "file": ("fallback_test.pdf", io.BytesIO(sample_pdf_content), "application/pdf")
        }
        data = {"notebook_id": str(test_notebook.id)}
        
        response = await client.post(
            "/api/v1/documents/upload",
            files=files,
            data=data
        )
        
        assert response.status_code == 200
        result = response.json()
        
        # Task ID should NOT be present
        assert "task_id" not in result
        assert result["status"] == "uploaded"
        
        # Document should still be created
        doc = await db_session.get(Document, result["document_id"])
        assert doc is not None
        assert doc.status == ProcessingStatus.PENDING

@pytest.mark.asyncio
async def test_queue_resilience_with_closed_app(
    client: AsyncClient, 
    test_notebook, 
    sample_pdf_content,
    mock_storage_service,
    db_session
):
    """
    Test what happens if Proc App is NOT open (simulating connection failure).
    Router should log error and fallback to BackgroundTasks.
    """
    # Ensure proc_app is CLOSED by NOT using the fixture
    
    with patch("src.routers.documents.USE_TASK_QUEUE", True):
        # We mock defer_async to raise exception because relying on "closed app" behavior 
        # depends on procrastinate implementation (it might auto-open).
        # To be safe and deterministic, we simulate the failure.
        with patch("src.services.queue.tasks.process_document_task.defer_async", side_effect=Exception("Connection Closed")):
            
            files = {
                "file": ("resilience_test.pdf", io.BytesIO(sample_pdf_content), "application/pdf")
            }
            data = {"notebook_id": str(test_notebook.id)}
            
            response = await client.post(
                "/api/v1/documents/upload",
                files=files,
                data=data
            )
            
            # Should fallback successfully
            assert response.status_code == 200
            result = response.json()
            assert "task_id" not in result

@pytest.mark.asyncio
async def test_full_production_flow(
    client: AsyncClient,
    test_notebook,
    test_user,
    db_session,
    open_proc_app
):
    """
    FULL E2E PRODUCTION FLOW:
    1. Upload raft.pdf (Real File)
    2. Enqueue Document Processing Task
    3. Run Worker -> Process Document -> Status COMPLETED
    4. Trigger Podcast Generation
    5. Run Worker -> Generate Podcast -> Status COMPLETED
    """
    
    # Path to real file
    raft_path = Path(r"D:\code\notebookllm\backend\data\uploads\raft.pdf")
    if not raft_path.exists():
        pytest.skip("raft.pdf not found, skipping E2E test")

    with open(raft_path, "rb") as f:
        pdf_content = f.read()

    # 1. Upload
    with patch("src.routers.documents.USE_TASK_QUEUE", True):
        # We mock storage to simply support the flow, but allow "real" processing logic
        with patch("src.routers.documents.get_storage_service") as mock_get_storage:
            with patch("src.services.queue.tasks.get_storage_service") as mock_task_storage:
                
                mock_storage = AsyncMock()
                mock_get_storage.return_value = mock_storage
                mock_task_storage.return_value = mock_storage
                
                # Upload simply returns success
                mock_storage.upload_stream.return_value = None
                
                # IMPORTANT: download_to_temp must create a real file for MainProcessor
                async def fake_download(path, bucket):
                    temp_path = Path(f"temp_{uuid.uuid4()}.pdf")
                    with open(temp_path, "wb") as tf:
                        tf.write(pdf_content)
                    return temp_path
                
                mock_storage.download_to_temp.side_effect = fake_download
                
                # --- Step 1: Upload ---
                print("\n[Test] Uploading document...")
                files = {"file": ("raft.pdf", io.BytesIO(pdf_content), "application/pdf")}
                resp = await client.post(
                    "/api/v1/documents/upload",
                    files=files,
                    data={"notebook_id": str(test_notebook.id)}
                )
                assert resp.status_code == 200
                doc_id = resp.json()["document_id"]
                task_id = resp.json()["task_id"]
                print(f"[Test] Uploaded Doc ID: {doc_id}, Task ID: {task_id}")

                # --- Step 2: Run Worker for Document ---
                print("[Test] Running worker for Document Processing...")
                
                # Create a task to run the worker
                # queues=['critical', 'default']
                worker_task = asyncio.create_task(
                    proc_app.run_worker_async(queues=["critical", "default"], wait=False)
                )
                
                # Wait for DB status to update
                max_retries = 30
                for i in range(max_retries):
                    await asyncio.sleep(1)
                    # Refresh to get latest status
                    # We must use db_session.get to avoid stale object
                    doc = await db_session.get(Document, doc_id)
                    
                    if doc.status == ProcessingStatus.COMPLETED:
                        print(f"[Test] Document Processing Completed! Chunks: {doc.chunk_count}")
                        break
                    if doc.status == ProcessingStatus.FAILED:
                        print(f"[Test] Document Failed: {doc.error_message}")
                        pytest.fail(f"Document processing failed: {doc.error_message}")
                else:
                    worker_task.cancel()
                    pytest.fail("Document processing timed out")

                # Verify Chunks created (Real Processing happened!)
                assert doc.chunk_count > 0

                # --- Step 3: Trigger Content Generation ---
                print("[Test] Triggering Podcast Generation...")
                
                # We need to ensure USE_TASK_QUEUE is True for Generation router too
                with patch("src.routers.generation.USE_TASK_QUEUE", True):
                    gen_resp = await client.post(
                        f"/api/v1/generation/{test_notebook.id}/generate",
                        json={
                            "content_type": "podcast",
                            "document_ids": [doc_id]
                        },
                        params={"async_mode": True}
                    )
                    assert gen_resp.status_code == 200
                    gen_data = gen_resp.json()
                    content_id = gen_data["content_id"]
                    gen_task_id = gen_data["task_id"]
                    print(f"[Test] Queued Podcast. Content ID: {content_id}, Task ID: {gen_task_id}")

                    # --- Step 4: Run Worker for Podcast ---
                    # Worker is still running. It should pick up the new job.
                    
                    # Wait for Content Completion
                    print("[Test] Waiting for Podcast Generation...")
                    for i in range(60): # 60s
                        await asyncio.sleep(1)
                        content = await db_session.get(GeneratedContent, content_id)
                        if content.status == ProcessingStatus.COMPLETED:
                            print(f"[Test] Podcast Generated! URL: {content.audio_url}")
                            # Clean up
                            break
                        if content.status == ProcessingStatus.FAILED:
                            # If failed, print error
                            print("Podcast generation failed.")
                            
                            # Note: To debug why, we'd need to check logs, but here we just fail
                            # Wait, GeneratedContent doesn't have error_message field usually? 
                            # Checking model... it probably does or status implies.
                            break
                    else:
                        worker_task.cancel()
                        pytest.fail("Podcast generation timed out")

                    # Stop worker
                    worker_task.cancel()
                    try:
                        await worker_task
                    except asyncio.CancelledError:
                        pass
                    
                    if content.status != ProcessingStatus.COMPLETED:
                         pytest.fail("Podcast generation Failed")
