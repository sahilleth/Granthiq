from typing import List, Optional, Set
from uuid import UUID
from datetime import datetime, timezone
from sqlmodel import select, desc, delete, or_, col
from sqlalchemy import text
from src.db.models import Notebook, TaskProgress, Document, GeneratedContent
from src.db.repositories.base import BaseRepository
from loguru import logger


class NotebookRepository(BaseRepository[Notebook]):
    """
    Repository for Notebook operations.
    """

    # Allowed filter fields for security (prevents SQL injection)
    ALLOWED_FILTER_FIELDS: Set[str] = {
        "user_id",
        "title",
    }

    def __init__(self, session):
        super().__init__(session, Notebook)

    async def get_user_notebooks(self, user_id: UUID) -> List[Notebook]:
        """Get all notebooks for a specific user, ordered by updated_at desc."""
        statement = (
            select(Notebook)
            .where(Notebook.user_id == user_id)
            .order_by(desc(Notebook.updated_at))
        )
        result = await self.session.exec(statement)
        return result.all()

    async def count_user_notebooks(self, user_id: UUID) -> int:
        """Count total notebooks for a specific user."""
        statement = select(Notebook).where(Notebook.user_id == user_id)
        result = await self.session.exec(statement)
        return len(result.all())

    async def get_user_notebooks_paginated(
        self, user_id: UUID, limit: int = 20, offset: int = 0
    ) -> List[Notebook]:
        """Get notebooks for a user with cursor-based pagination."""
        statement = (
            select(Notebook)
            .where(Notebook.user_id == user_id)
            .order_by(desc(Notebook.updated_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.exec(statement)
        return result.all()

    async def update_settings(
        self, notebook_id: UUID, settings: dict
    ) -> Optional[Notebook]:
        """Update RAG settings for a notebook."""
        return await self.update(
            notebook_id,
            {"settings": settings, "updated_at": datetime.now(timezone.utc)},
        )

    async def create_notebook(
        self, user_id: UUID, title: str = "Untitled Notebook"
    ) -> Notebook:
        """Create a new notebook for a user."""
        notebook = Notebook(user_id=user_id, title=title)
        return await self.create(notebook)

    async def get_notebook(
        self, notebook_id: UUID, user_id: Optional[UUID] = None
    ) -> Optional[Notebook]:
        """
        Get a notebook by ID, optionally verifying ownership.
        If user_id is provided, returns None if the notebook doesn't belong to that user.
        """
        notebook = await self.get(notebook_id)
        if not notebook:
            return None

        if user_id is not None and notebook.user_id != user_id:
            return None

        return notebook

    async def get_notebooks(
        self, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> List[Notebook]:
        """Get all notebooks for a user with pagination."""
        return await self.get_user_notebooks_paginated(user_id, limit, offset)

    async def delete_notebook(self, notebook_id: UUID, user_id: UUID) -> bool:
        """
        Delete a notebook and all its related data.
        Clears task_progress rows first to avoid FK constraint violations,
        then lets the ORM cascade handle the rest.
        """
        notebook = await self.get(notebook_id)
        if not notebook:
            return False

        if notebook.user_id != user_id:
            return False

        # Collect IDs of all child documents and generated content
        doc_result = await self.session.exec(
            select(Document.id).where(Document.notebook_id == notebook_id)
        )
        doc_ids = list(doc_result.all())

        content_result = await self.session.exec(
            select(GeneratedContent.id).where(GeneratedContent.notebook_id == notebook_id)
        )
        content_ids = list(content_result.all())

        # Build OR conditions for all FK references in task_progress
        conditions = [TaskProgress.notebook_id == notebook_id]
        if doc_ids:
            conditions.append(col(TaskProgress.document_id).in_(doc_ids))
        if content_ids:
            conditions.append(col(TaskProgress.content_id).in_(content_ids))

        await self.session.exec(
            delete(TaskProgress).where(or_(*conditions))
        )
        logger.info(f"Cleared task_progress for notebook {notebook_id} (docs={len(doc_ids)}, content={len(content_ids)})")

        return await self.delete(notebook_id)
