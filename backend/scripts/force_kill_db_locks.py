import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Add backend directory to sys.path to allow importing src
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.append(backend_dir)

from src.config import get_settings

async def kill_locks():
    settings = get_settings()
    db_url = settings.database.url
    
    if not db_url:
        print("Error: No database URL found in settings.")
        return

    print(f"Connecting to database to clear locks...")
    
    # Use isolation_level="AUTOCOMMIT" to run independent commands like pg_terminate_backend
    engine = create_async_engine(db_url, isolation_level="AUTOCOMMIT")

    try:
        async with engine.connect() as conn:
            # Query to terminate all other connections to the current database
            terminate_query = text("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                AND pid <> pg_backend_pid();
            """)
            
            # Execute the query
            await conn.execute(terminate_query)
            print("Successfully terminated all other database connections.")
            
    except Exception as e:
        print(f"Error terminating connections: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(kill_locks())
