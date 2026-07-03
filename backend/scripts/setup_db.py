import asyncio
import sys
import os
import logging
from urllib.parse import urlparse
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

# 1. Setup paths so we can import from src
# This ensures we can run this script from the root directory or inside scripts/
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Load environment variables
load_dotenv()

# 2. Import Project Modules
# We import settings to see what the app sees, and engine to connect
try:
    from src.config import get_settings
    from src.db.session import engine
    from sqlmodel import SQLModel
    # IMPORTS: Must import models so they register with SQLModel.metadata
    from src.db.models import User, Notebook, Document, ChatMessage, GeneratedContent, MessageCitation
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("   Make sure you are running this from the project root (e.g., 'python scripts/setup_db.py')")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("setup_db")

async def setup_database():
    """
    Creates tables in the Supabase/PostgreSQL database.
    """
    settings = get_settings()
    db_url = settings.database.url

    if not db_url:
        logger.error("❌ DATABASE_URL is not set in .env or config.")
        return

    # 3. Analyze Connection String for Debugging
    try:
        # Mask password for logging
        if "://" in db_url:
            scheme, rest = db_url.split("://", 1)
            if "@" in rest:
                auth, location = rest.split("@", 1)
                if ":" in auth:
                    user, _ = auth.split(":", 1)
                    safe_url = f"{scheme}://{user}:******@{location}"
                else:
                    safe_url = f"{scheme}://{auth}:******@{location}"
            else:
                safe_url = db_url
        else:
            safe_url = "Invalid URL Format"

        logger.info(f"🔌 Target Database: {safe_url}")

        # Check for correct Async Driver
        if "postgresql" in db_url and "asyncpg" not in db_url:
            logger.warning("⚠️  WARNING: URL does not contain 'asyncpg'.")
            logger.warning("   Supabase Async requires: postgresql+asyncpg://user:pass@host:5432/db")

    except Exception:
        logger.warning(f"   Could not parse URL for logging.")

    # 4. Check Metadata (Tables to be created)
    tables = list(SQLModel.metadata.tables.keys())
    logger.info(f"📋 Schema contains {len(tables)} tables:")
    for t in tables:
        logger.info(f"   - {t}")

    if not tables:
        logger.error("❌ No tables found in metadata! Check src/db/models.py imports.")
        return

    # 5. Connect and Create
    try:
        logger.info("⏳ Connecting to Supabase...")
        
        async with engine.begin() as conn:
            # Simple health check
            await conn.execute(text("SELECT 1"))
            logger.info("✅ Connected successfully.")

            logger.info("🚀 Running 'create_all' (Safe: only creates missing tables)...")
            await conn.run_sync(SQLModel.metadata.create_all)
            
            logger.info("✅ Database schema synced successfully!")
            logger.info("   Note: If you need to modify existing columns, use Alembic migrations.")

    except OperationalError as e:
        logger.error(f"❌ Connection Failed: {e}")
        logger.error("   Checklist:")
        logger.error("   1. Is the password correct? (Special characters must be URL-encoded)")
        logger.error("   2. Is Port 5432 used? (Port 6543 requires a different setup)")
        logger.error("   3. Is 'SSL mode' enabled in the engine args?")
    except Exception as e:
        logger.exception(f"❌ Unexpected Error: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    # Fix for Windows Asyncio Loop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(setup_database())