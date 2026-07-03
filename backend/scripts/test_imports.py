print("1. Start")
import sys
import os
sys.path.append(os.getcwd())
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
print("2. Policy Set")

from src.services.queue.app import proc_app
print("3. App Imported")

from src.db.session import async_session_factory
print("4. Session Imported")

from src.services.queue.worker import recover_dead_jobs
print("5. Worker Imported")
