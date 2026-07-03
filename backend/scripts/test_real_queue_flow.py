import asyncio
import os
import sys
import shutil
import uuid
from pathlib import Path
from typing import Optional
import httpx
import subprocess
import time
from sqlalchemy import text
from functools import partial

# Add backend to python path
BACKEND_DIR = Path(__file__).parent.parent
sys.path.append(str(BACKEND_DIR))

# Import needed modules
from src.db.session import async_session_factory
from src.db.models import Document, GeneratedContent, ProcessingStatus

# Constants
API_BASE = "http://localhost:8000/api/v1"
TEST_USER_ID = "1504830e-2f2a-426b-a934-0625a3cb9812" # Using notebook ID as user ID for simplicity? No, confusing.
# Let's use clean IDs
FIXED_USER_ID = "eaa585c2-9a2c-445e-9b8c-eaf5bb6bf4fa"
FIXED_NOTEBOOK_ID = "1504830e-2f2a-426b-a934-0625a3cb9812"

RAFT_PDF_PATH = Path(r"D:\code\notebookllm\backend\data\uploads\raft.pdf")

# Env vars for worker
ENV = os.environ.copy()
ENV["USE_TASK_QUEUE"] = "true"
# ENV["DATABASE_URL"] should be set in current shell, otherwise hardcode

async def setup_db_data():
    """Ensure User and Notebook exist."""
    print("Setting up DB data...")
    async with async_session_factory() as session:
        # Check User
        result = await session.execute(text(f"SELECT id FROM user_table WHERE id = '{FIXED_USER_ID}'")) # 'user' is reserved keyword often
        # Wait, model is 'User' table 'user' usually.
        # Let's check table name. Models default to class name lower? 'user'
        # user is reserved in Postgres. models.py uses `class User(SQLModel, table=True):`
        # SQLModel usually quotes it. Or uses 'user'.
        # I'll use simple check.
        try:
             # Just try to insert, ignore conflict
             await session.execute(text(f"INSERT INTO \"user\" (id, email, hashed_password, is_active) VALUES ('{FIXED_USER_ID}', 'test@example.com', 'hash', true) ON CONFLICT (id) DO NOTHING"))
             await session.execute(text(f"INSERT INTO notebook (id, user_id, title) VALUES ('{FIXED_NOTEBOOK_ID}', '{FIXED_USER_ID}', 'E2E Test Notebook') ON CONFLICT (id) DO NOTHING"))
             await session.commit()
             print("DB Data ensured.")
        except Exception as e:
            print(f"DB Setup warning (might already exist): {e}")

async def upload_document(client: httpx.AsyncClient) -> str:
    """Upload raft.pdf and return document_id."""
    print(f"Uploading {RAFT_PDF_PATH}...")
    if not RAFT_PDF_PATH.exists():
        raise FileNotFoundError(f"File not found: {RAFT_PDF_PATH}")
    
    files = {"file": ("raft.pdf", open(RAFT_PDF_PATH, "rb"), "application/pdf")}
    data = {"notebook_id": FIXED_NOTEBOOK_ID}
    
    # We need authentication? Depends on `get_current_user` mock or implementation.
    # In dev, maybe we can hack headers?
    # Or assuming we run against a server with auth disabled?
    # Actually, `test_queue_processing.py` worked because it mocked `get_current_user`.
    # A REAL script hitting localhost:8000 needs a JWT token.
    # Generating a token manually?
    
    # Alternative: Use "Login" endpoint if available?
    # Or override dependency in the RUNNING server? No, server is running independently?
    # Wait, is the server running?
    # The user said "use actual db". They didn't say "use running server".
    # I can use `httpx.ASGITransport(app=app)` to run IN PROCESS!
    # Yes, that's better. "Real DB" doesn't mean "Real HTTP Server process".
    # I can use `app` from `src.app`.
    print("Uploading via internal ASGI client...")
    return "PENDING"

# Refactoring: Run everything in-process using ASGITransport, but spawn WORKER separately.
from src.app import create_app
from src.services.auth import get_current_user

app = create_app()

# Override auth to return our fixed user
async def override_get_current_user():
    return uuid.UUID(FIXED_USER_ID)

app.dependency_overrides[get_current_user] = override_get_current_user

async def run_flow():
    # 1. Setup DB
    await setup_db_data()
    
    # Start Worker Process
    print("\n[Worker] Starting Procrastinate Worker...")
    worker_cmd = [
        sys.executable, "-m", "procrastinate", 
        "--app", "src.services.queue.app.proc_app", 
        "worker"
    ]
    worker_process = subprocess.Popen(
        worker_cmd, 
        cwd=BACKEND_DIR,
        env=ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    # We'll read output later or let it stream?
    # Popen with PIPES might buffer.
    
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            
            # 2. Upload Document
            with open(RAFT_PDF_PATH, "rb") as f:
                response = await client.post(
                    "/api/v1/documents/upload",
                    files={"file": ("raft.pdf", f, "application/pdf")},
                    data={"notebook_id": FIXED_NOTEBOOK_ID}
                )
            
            if response.status_code not in [200, 201]:
                print(f"Upload failed: {response.text}")
                return
            
            doc_data = response.json()
            doc_id = doc_data["document_id"]
            print(f"[Upload] Success. Doc ID: {doc_id}. Task ID: {doc_data.get('task_id')}")
            
            # 3. Wait for processing COMPLETION
            print("\n[Wait] Waiting for Document Processing...")
            start_time = time.time()
            while time.time() - start_time < 60: # 60s timeout
                # Check DB directly
                async with async_session_factory() as session:
                    doc = await session.get(Document, uuid.UUID(doc_id))
                    if doc and doc.status == ProcessingStatus.COMPLETED:
                        print(f"[Success] Document {doc_id} is COMPLETED!")
                        print(f"  Chunk count: {doc.chunk_count}")
                        break
                    if doc and doc.status == ProcessingStatus.FAILED:
                        print(f"[Fail] Document processing FAILED.")
                        break
                    print(f"  Status: {doc.status if doc else 'None'}...")
                await asyncio.sleep(2)
            else:
                print("[Timeout] Document processing timed out.")
                
            
            # 4. Trigger Podcast Generation
            print("\n[Generate] Requesting Podcast...")
            gen_resp = await client.post(
                f"/api/v1/generation/{FIXED_NOTEBOOK_ID}/generate",
                json={
                    "content_type": "podcast",
                    "document_ids": [doc_id]
                },
                params={"async_mode": True} # Force async
            )
            
            if gen_resp.status_code != 200:
                print(f"Generation request failed: {gen_resp.text}")
                return
                
            gen_data = gen_resp.json()
            content_id = gen_data["content_id"]
            task_id = gen_data.get("task_id")
            print(f"[Generate] Queued. Content ID: {content_id}. Task ID: {task_id}")
            
            # 5. Wait for Content
            print("\n[Wait] Waiting for Podcast Generation...")
            start_time = time.time()
            while time.time() - start_time < 120: # 2m timeout (podcasts are slow)
                async with async_session_factory() as session:
                    content = await session.get(GeneratedContent, uuid.UUID(content_id))
                    if content and content.status == ProcessingStatus.COMPLETED:
                        print(f"[Success] Podcast Generated!")
                        print(f"  Audio URL: {content.audio_url}")
                        print(f"  Script length: {len(str(content.content))}")
                        break
                    if content and content.status == ProcessingStatus.FAILED:
                        print(f"[Fail] Generation FAILED.")
                        break
                    print(f"  Gen Status: {content.status if content else 'None'}...")
                await asyncio.sleep(3)
            
    finally:
        print("\n[Cleanup] Stopping Worker...")
        worker_process.terminate()
        try:
            worker_process.wait(timeout=5)
        except:
            worker_process.kill()
        
        # Print worker errors if any
        stderr = worker_process.stderr.read()
        if stderr:
             print(f"Worker Stderr:\n{stderr.decode()}")

if __name__ == "__main__":
    asyncio.run(run_flow())
