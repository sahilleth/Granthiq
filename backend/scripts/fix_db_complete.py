import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from sqlalchemy import text
from src.db.session import async_session_factory

async def main():
    print("Fixing Alembic version...")
    
    async with async_session_factory() as session:
        # Update alembic version
        await session.execute(text("UPDATE alembic_version SET version_num = '06998810b3f7'"))
        await session.commit()
        
        # Verify
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        current = result.scalar()
        print(f"✓ Alembic version reset to: {current}")
        
        # Now create the enum type
        print("\nCreating chatrole enum type...")
        try:
            await session.execute(text("CREATE TYPE chatrole AS ENUM ('user', 'assistant')"))
            await session.commit()
            print("✓ Created chatrole enum")
        except Exception as e:
            if "already exists" in str(e):
                print("✓ chatrole enum already exists")
                await session.rollback()
            else:
                print(f"Error creating enum: {e}")
                raise
        
        # Alter the column
        print("\nUpdating chatmessage table...")
        try:
            await session.execute(text("ALTER TABLE chatmessage ALTER COLUMN role TYPE chatrole USING role::chatrole"))
            await session.commit()
            print("✓ Updated chatmessage.role column to use chatrole enum")
        except Exception as e:
            print(f"Error altering column: {e}")
            await session.rollback()
            raise
        
        # Update alembic version to new migration
        await session.execute(text("UPDATE alembic_version SET version_num = '2f3e4d5c6a7b'"))
        await session.commit()
        print("\n✓ Updated Alembic version to 2f3e4d5c6a7b")

if __name__ == "__main__":
    asyncio.run(main())
