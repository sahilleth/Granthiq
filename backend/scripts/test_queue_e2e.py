import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

# Fix for psycopg async support on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), ""))

from src.db.session import async_session_factory
from src.db.models import User, Notebook, Document, ProcessingStatus
from src.services.queue.tasks import process_document_task
from src.services.queue.app import proc_app
from src.db.repositories.task_progress import TaskProgressRepository
from sqlmodel import select

async def create_test_data(session):
    # Create dummy user
    user = User(email=f"queue_test_{uuid4()}@example.com", hashed_password="test")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    # Create dummy notebook
    notebook = Notebook(user_id=user.id, name="Queue Test NB")
    session.add(notebook)
    await session.commit()
    await session.refresh(notebook)
    
    # Create dummy document
    doc = Document(
        notebook_id=notebook.id,
        filename="test.txt",
        file_path="test/path.txt",
        mime_type="text/plain",
        status=ProcessingStatus.PENDING,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    
    return user, notebook, doc

async def monitor_task(job_id):
    print(f"Monitoring Job ID: {job_id}")
    
    async with async_session_factory() as session:
        repo = TaskProgressRepository(session)
        
        for i in range(120): # Wait up to 120 seconds
            await asyncio.sleep(1)
            
            # Check TaskProgress
            progress = await repo.get_by_job_id(job_id)
            if progress:
                print(f"[{i}s] Progress: {progress.progress_percent}% - {progress.message}")
                
                if progress.progress_percent == 100:
                    print(" [SUCCESS] Task Completed Successfully!")
                    return True
                
                if progress.message and progress.message.startswith("Failed:"):
                    print(f" [SUCCESS (Expected Error)] Task Failed (as expected for missing file): {progress.message}")
                    return True # Returning True because the queue mechanism worked!
            else:
                 print(f"[{i}s] Waiting for worker to pick up job...")
                 
    print("timed out waiting for task completion")
    return False

async def main():
    print("Starting Queue E2E Test")
    
    async with async_session_factory() as session:
        print("1. Creating test data...")
        user, notebook, doc = await create_test_data(session)
        print(f"   Created Document: {doc.id}")

        print("2. Enqueuing task...")
        # Must open app to defer tasks
        async with proc_app.open_async():
            # deeper_async returns a job instance
            job = await process_document_task.defer_async(
                document_id=str(doc.id),
                user_id=str(user.id),
                storage_path="test/path.txt", 
                file_path=None 
            )
        
        print(f"   Job Enqueued! ID: {job}")
        
        print("3. Waiting for worker processing...")
        # The worker needs to be running in a separate terminal!
        await monitor_task(job)

if __name__ == "__main__":
    current_dir = os.getcwd()
    sys.path.append(current_dir)
    asyncio.run(main())
