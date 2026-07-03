
import asyncio
import io
import os
import sys
import uuid
import contextlib
from pathlib import Path

# Add backend to sys.path
BACKEND_DIR = Path(__file__).parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

async def run_e2e_test():
    print("Starting E2E Queue Test...")
    
    # Lazy imports to avoid top-level crash
    from httpx import AsyncClient, ASGITransport
    from src.app import create_app
    from src.services.auth import get_current_user
    from src.db.session import get_session, async_session_factory
    from src.db.models import Document, ProcessingStatus, GeneratedContent
    from src.db.repositories.notebook import NotebookRepository
    from src.db.repositories.document import DocumentRepository
    from src.services.queue.app import proc_app
    from tests.conftest import TEST_USER_ID, ensure_test_user_exists, utc_now
    from src.db.models import Notebook, ProcessingStatus
    from src.schemas.document import UnifiedDocument, DocumentChunk
    from unittest.mock import AsyncMock, patch, MagicMock

    # 1. Setup DB User/Notebook
    print("[Setup] DB...")
    async with async_session_factory() as session:
         await ensure_test_user_exists(session)
    
    # Setup App
    app = create_app()
    
    async def override_get_current_user():
        return TEST_USER_ID
        
    async def override_get_session():
        async with async_session_factory() as session:
            yield session
            
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_session] = override_get_session
    
    transport = ASGITransport(app=app)
    
    # Create Notebook with fixed ID
    FIXED_NOTEBOOK_ID = uuid.UUID("1504830e-2f2a-426b-a934-0625a3cb9812")
    
    async with async_session_factory() as session:
        notebook_repo = NotebookRepository(session)
        notebook = await notebook_repo.get_notebook(FIXED_NOTEBOOK_ID, TEST_USER_ID)
        if not notebook:
            notebook = Notebook(
                    id=FIXED_NOTEBOOK_ID,
                    user_id=TEST_USER_ID,
                    title="E2E Test Notebook",
                    created_at=utc_now(),
                    updated_at=utc_now()
            )
            session.add(notebook)
            await session.commit()
            print(f"[Setup] Created notebook {FIXED_NOTEBOOK_ID}")
        else:
            print(f"[Setup] Using existing notebook {FIXED_NOTEBOOK_ID}")
            
    # 2. Upload Flow
    raft_path = BACKEND_DIR / "data" / "uploads" / "raft.pdf"
    if not raft_path.exists():
        print(f"[Skip] {raft_path} not found.")
        return

    with open(raft_path, "rb") as f:
        pdf_content = f.read()
        
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Start Worker (via proc_app directly)
        print("[Worker] Starting Procrastinate worker task...")
        # We need to open the app first?
        # proc_app.open_async() is context manager.
        async with proc_app.open_async():
             # Setup Mocks Persistently (only essential ones - let document processing be real)
             patcher_use_queue_doc = patch("src.routers.documents.USE_TASK_QUEUE", True)
             patcher_use_queue_gen = patch("src.routers.generation.USE_TASK_QUEUE", True)
             patcher_get_storage = patch("src.routers.documents.get_storage_service")
             patcher_task_storage = patch("src.services.queue.tasks.get_storage_service")
             patcher_httpx = patch("httpx.AsyncClient", autospec=True) # Patch global httpx
             
             worker_task = None
             
             try:
                 patcher_use_queue_doc.start()
                 patcher_use_queue_gen.start()
                 mock_get_storage = patcher_get_storage.start()
                 mock_task_storage = patcher_task_storage.start()
                 mock_httpx_cls = patcher_httpx.start()
                 
                 # Mock Httpx Client (for download) - returns actual PDF content
                 mock_httpx_instance = AsyncMock()
                 mock_httpx_cls.return_value.__aenter__.return_value = mock_httpx_instance
                 
                 @contextlib.asynccontextmanager
                 async def fake_stream_download(method, url):
                     mock_resp = AsyncMock()
                     # Mock aiter_bytes to return actual PDF content
                     async def iter_bytes():
                         yield pdf_content
                     mock_resp.aiter_bytes = iter_bytes
                     mock_resp.raise_for_status = MagicMock()
                     yield mock_resp

                 mock_httpx_instance.stream = MagicMock(side_effect=fake_stream_download)

                 # Mock Storage Service
                 mock_storage = AsyncMock()
                 mock_get_storage.return_value = mock_storage
                 mock_task_storage.return_value = mock_storage
                 
                 mock_storage.upload_stream.return_value = None
                 mock_storage.get_url.return_value = "http://mock"
                 
                 async def fake_download(path, bucket):
                    tpath = Path(f"temp_{uuid.uuid4()}.pdf")
                    with open(tpath, "wb") as f:
                        f.write(pdf_content)
                    return tpath
                 mock_storage.download_to_temp.side_effect = fake_download
                 
                 # Start worker in background (attempt)
                 # IMPORTANT: listen_notify=False to avoid Windows/psycopg errors
                 worker_task = asyncio.create_task(
                     proc_app.run_worker_async(
                         queues=["critical", "default"], 
                         wait=False,
                         listen_notify=False  # Disable LISTEN/NOTIFY - use polling instead
                     )
                 )

                 # Upload
                 print("\n[Step 1] Uploading Document...")
                 files = {"file": ("raft.pdf", io.BytesIO(pdf_content), "application/pdf")}
                 resp = await client.post(
                     "/api/v1/documents/upload",
                     files=files,
                     data={"notebook_id": str(FIXED_NOTEBOOK_ID)}
                 )
                 if resp.status_code != 200:
                     print(f"Upload failed: {resp.text}")
                     return
                 
                 doc_id = resp.json()["document_id"]
                 task_id = resp.json().get("task_id")
                 print(f"  -> Uploaded. DocID: {doc_id}, TaskID: {task_id}")
                 
                 # Wait for Processing (real PDF takes ~4 minutes)
                 print("\n[Step 2] Waiting for Document Processing...")
                 for i in range(360):  # 6 minutes timeout for real PDF processing
                     await asyncio.sleep(1)
                     async with async_session_factory() as session:
                             doc = await session.get(Document, uuid.UUID(doc_id))
                             if doc and doc.status == ProcessingStatus.COMPLETED:
                                 print(f"  -> COMPLETED! Chunks: {doc.chunk_count}")
                                 break
                             if doc and doc.status == ProcessingStatus.FAILED:
                                 print(f"  -> FAILED: {doc.error_message}")
                                 if "getaddrinfo" in str(doc.error_message):
                                     print("     (Mock failed to apply to worker/background task)")
                                 return
                 else:
                     print("  -> Timeout waiting for document.")
                     return

                 # Trigger Generation (Podcast)
                 print("\n[Step 3] Triggering Podcast Generation...")
                 gen_resp = await client.post(
                     f"/api/v1/generation/{FIXED_NOTEBOOK_ID}/generate",
                     json={"content_type": "podcast", "document_ids": [doc_id]},
                     params={"async_mode": True}
                 )
                 
                 if gen_resp.status_code != 200:
                      print(f"Gen failed: {gen_resp.text}")
                      return

                 content_id = gen_resp.json()["content_id"]
                 print(f"  -> Queued. ContentID: {content_id}")
                 
                 # Wait for Podcast
                 print("\n[Step 4] Waiting for Podcast Generation...")
                 for i in range(120):
                     await asyncio.sleep(1)
                     async with async_session_factory() as session:
                         content = await session.get(GeneratedContent, uuid.UUID(content_id))
                         if content and content.status == ProcessingStatus.COMPLETED:
                             print(f"  -> PODCAST GENERATED! URL: {content.audio_url}")
                             print(f"  Script Preview: {str(content.content)[:100]}...")
                             break
                         if content and content.status == ProcessingStatus.FAILED:
                             print(f"  -> FAILED. (Check logs)")
                             break
                 else:
                     print("  -> Timeout waiting for podcast.")

             finally:
                 print("\nstopping worker...")
                 # Stop patchers
                 patcher_use_queue_doc.stop()
                 patcher_use_queue_gen.stop()
                 patcher_get_storage.stop()
                 patcher_task_storage.stop()
                 patcher_httpx.stop()
                 
                 if worker_task:
                     worker_task.cancel()
                     try:
                         await worker_task
                     except:
                         pass

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(run_e2e_test())
    except Exception as e:
        import traceback
        traceback.print_exc()

