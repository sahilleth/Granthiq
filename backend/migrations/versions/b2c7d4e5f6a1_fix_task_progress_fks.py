"""Fix task_progress foreign keys

Revision ID: b2c7d4e5f6a1
Revises: 09c618e11b5a
Create Date: 2026-01-14 22:00:00.000000

Adds missing user_id and notebook_id columns with foreign key constraints,
and adds proper foreign key constraints for document_id and content_id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c7d4e5f6a1'
down_revision: Union[str, Sequence[str], None] = '09c618e11b5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing columns and foreign keys to task_progress table."""
    # Add user_id column
    op.add_column(
        'task_progress',
        sa.Column('user_id', sa.Uuid(), nullable=True)
    )
    op.create_index(
        op.f('ix_task_progress_user_id'),
        'task_progress',
        ['user_id'],
        unique=False
    )

    # Add notebook_id column
    op.add_column(
        'task_progress',
        sa.Column('notebook_id', sa.Uuid(), nullable=True)
    )
    op.create_index(
        op.f('ix_task_progress_notebook_id'),
        'task_progress',
        ['notebook_id'],
        unique=False
    )

    # Add foreign key constraints
    # Note: These are optional FKs (SET NULL on delete) since tasks
    # can reference entities that may be deleted
    op.create_foreign_key(
        'fk_task_progress_user_id',
        'task_progress', 'user',
        ['user_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_task_progress_notebook_id',
        'task_progress', 'notebook',
        ['notebook_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_task_progress_document_id',
        'task_progress', 'document',
        ['document_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_task_progress_content_id',
        'task_progress', 'generatedcontent',
        ['content_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Remove foreign keys and columns added in this migration."""
    # Drop foreign keys first
    op.drop_constraint('fk_task_progress_content_id', 'task_progress', type_='foreignkey')
    op.drop_constraint('fk_task_progress_document_id', 'task_progress', type_='foreignkey')
    op.drop_constraint('fk_task_progress_notebook_id', 'task_progress', type_='foreignkey')
    op.drop_constraint('fk_task_progress_user_id', 'task_progress', type_='foreignkey')

    # Drop indexes
    op.drop_index(op.f('ix_task_progress_notebook_id'), table_name='task_progress')
    op.drop_index(op.f('ix_task_progress_user_id'), table_name='task_progress')

    # Drop columns
    op.drop_column('task_progress', 'notebook_id')
    op.drop_column('task_progress', 'user_id')
