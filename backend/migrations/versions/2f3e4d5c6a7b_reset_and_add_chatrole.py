"""Reset alembic version and add chatrole enum

Revision ID: 2f3e4d5c6a7b
Revises: 06998810b3f7
Create Date: 2026-01-15 19:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f3e4d5c6a7b'
down_revision: Union[str, Sequence[str], None] = '06998810b3f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the chatrole enum type
    op.execute("CREATE TYPE chatrole AS ENUM ('user', 'assistant')")
    
    # Alter the chatmessage table to use the enum type
    # The column currently stores 'user' and 'assistant' as text, so we can cast it
    op.execute("ALTER TABLE chatmessage ALTER COLUMN role TYPE chatrole USING role::chatrole")


def downgrade() -> None:
    """Downgrade schema."""
    # Revert the column to VARCHAR
    op.execute("ALTER TABLE chatmessage ALTER COLUMN role TYPE VARCHAR")
    
    # Drop the enum type
    op.execute("DROP TYPE chatrole")
