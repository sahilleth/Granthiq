import asyncio
import os
import sys
from uuid import uuid4
from pathlib import Path

# Force USE_TASK_QUEUE to true BEFORE importing application code
os.environ["USE_TASK_QUEUE"] = "true"

# Fix for psycopg async support on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), ""))

from src.db.session import async_session_factory
from src.db.models import User, Notebook, Document, ProcessingStatus
from src.db.repositories.task_progress import TaskProgressRepository
from src.routers.documents import schedule_document_processing
from src.services.queue.app import proc_app

async def create_test_data(session):
    # Create dummy user
    user = User(email=f"prod_flow_{uuid4()}@example.com", hashed_password="test")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    # Create dummy notebook
    notebook = Notebook(user_id=user.id, name="Prod Flow NB")
    session.add(notebook)
    await session.commit()
    await session.refresh(notebook)
    
    # Create dummy document (Simulating a file explicitly uploaded via API)
    doc = Document(
        notebook_id=notebook.id,
        filename="prod_test.txt",
        file_path="test/prod_path.txt",
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
                    return True
            else:
                 print(f"[{i}s] Waiting for worker to pick up job...")
                 
    print("timed out waiting for task completion")
    return False

async def main():
    print("Starting Cloud-Like Production Flow Test")
    print("(Testing integration between Router logic and Task Queue)")
    
    async with async_session_factory() as session:
        print("1. Creating test data (Simulating Upload)...")
        user, notebook, doc = await create_test_data(session)
        print(f"   Created Document: {doc.id}")

        print("2. Calling Router Schedule Logic...")
        
        # Open app context to allow deferring tasks
        async with proc_app.open_async():
            # This function is what the API endpoint calls
            task_id = await schedule_document_processing(
                document_id=doc.id,
                user_id=user.id,
                storage_path="test/prod_path.txt",
                bucket="notebook-private",
                notebook_id=notebook.id,
                background_tasks=None 
            )
        
        if task_id:
            print(f"   Router successfully enqueued task! ID: {task_id}")
        else:
            print("   ❌ Router FAILED to enqueue task (returned None)")
            return

        print("3. Waiting for worker processing...")
        await monitor_task(task_id)

if __name__ == "__main__":
    current_dir = os.getcwd()
    sys.path.append(current_dir)
    asyncio.run(main())
