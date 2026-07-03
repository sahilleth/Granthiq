import asyncio
import asyncpg
import os
from urllib.parse import urlparse

async def fix_alembic_version():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set")
        return
    
    # Parse the URL
    parsed = urlparse(db_url)
    
    # Connect using asyncpg
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/')
    )
    
    try:
        # Update the version
        await conn.execute("UPDATE alembic_version SET version_num = '06998810b3f7'")
        print("✓ Alembic version reset to 06998810b3f7")
        
        # Verify
        result = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"✓ Current version: {result}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_alembic_version())
