

from typing import Optional, Set
from uuid import UUID
from datetime import datetime
from sqlmodel import select, desc
from src.db.models import TaskProgress
from src.db.repositories.base import BaseRepository
from sqlalchemy import delete as sql_delete


class TaskProgressRepository(BaseRepository[TaskProgress]):
    """
    Repository for TaskProgress operations.

    Tracks progress of background tasks (document processing, content generation)
    to enable real-time progress updates in the frontend.
    """

    # Allowed filter fields for security (prevents SQL injection)
    ALLOWED_FILTER_FIELDS: Set[str] = {
        "job_id",
        "user_id",
        "notebook_id",
        "document_id",
        "content_id",
    }

    def __init__(self, session):
        super().__init__(session, TaskProgress)

    async def create_progress(
        self,
        job_id: int,
        user_id: Optional[UUID] = None,
        notebook_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None,
        content_id: Optional[UUID] = None,
        progress_percent: int = 0,
        message: str = "Task started"
    ) -> TaskProgress:
        """
        Create initial progress record for a task.

        Args:
            job_id: Procrastinate job ID
            user_id: Owner user ID (for authorization)
            notebook_id: Related notebook ID
            document_id: Related document ID (for document tasks)
            content_id: Related content ID (for generation tasks)
            progress_percent: Initial progress (0-100)
            message: Initial status message

        Returns:
            Created TaskProgress record
        """
        progress = TaskProgress(
            job_id=job_id,
            user_id=user_id,
            notebook_id=notebook_id,
            document_id=document_id,
            content_id=content_id,
            progress_percent=progress_percent,
            message=message
        )
        return await self.create(progress)

    async def update_progress(
        self,
        job_id: int,
        progress_percent: int,
        message: Optional[str] = None
    ) -> Optional[TaskProgress]:
        """
        Update progress for an existing task.

        Args:
            job_id: Procrastinate job ID
            progress_percent: New progress value (0-100)
            message: Optional new status message

        Returns:
            Updated TaskProgress record, or None if not found
        """
        # Find latest progress record for this job
        statement = (
            select(TaskProgress)
            .where(TaskProgress.job_id == job_id)
            .order_by(desc(TaskProgress.updated_at))
            .limit(1)
        )
        result = await self.session.exec(statement)
        progress = result.first()

        if not progress:
            return None

        # Update fields
        progress.progress_percent = min(100, max(0, progress_percent))
        progress.updated_at = datetime.utcnow()
        if message:
            progress.message = message

        self.session.add(progress)
        await self.session.commit()
        await self.session.refresh(progress)

        return progress

    async def get_by_job_id(self, job_id: int) -> Optional[TaskProgress]:
        """
        Get the latest progress for a job.

        Args:
            job_id: Procrastinate job ID

        Returns:
            Latest TaskProgress record, or None if not found
        """
        statement = (
            select(TaskProgress)
            .where(TaskProgress.job_id == job_id)
            .order_by(desc(TaskProgress.updated_at))
            .limit(1)
        )
        result = await self.session.exec(statement)
        return result.first()

    async def complete_progress(
        self,
        job_id: int,
        message: str = "Task completed successfully"
    ) -> Optional[TaskProgress]:
        """
        Mark task as complete (100%).

        Args:
            job_id: Procrastinate job ID
            message: Completion message

        Returns:
            Updated TaskProgress record
        """
        return await self.update_progress(job_id, 100, message)

    async def fail_progress(
        self,
        job_id: int,
        error_message: str
    ) -> Optional[TaskProgress]:
        """
        Mark task as failed with error message.

        Note: Progress percent is not changed, preserving where it failed.

        Args:
            job_id: Procrastinate job ID
            error_message: Error message to display

        Returns:
            Updated TaskProgress record
        """
        progress = await self.get_by_job_id(job_id)
        if not progress:
            return None

        progress.message = f"Failed: {error_message}"
        progress.updated_at = datetime.utcnow()

        self.session.add(progress)
        await self.session.commit()
        await self.session.refresh(progress)

        return progress

    async def delete_by_content_id(self, content_id: UUID) -> int:
        """
        Delete all TaskProgress records associated with a content_id.

        Used before deleting GeneratedContent to avoid FK constraint violations.

        Args:
            content_id: The content ID whose progress records should be deleted

        Returns:
            Number of records deleted
        """
      
        result = await self.session.execute(
            sql_delete(TaskProgress).where(TaskProgress.content_id == content_id)
        )
        await self.session.commit()
        return result.rowcount if hasattr(result, 'rowcount') else 0

    async def delete_by_document_id(self, document_id: UUID) -> int:
        """
        Delete all TaskProgress records associated with a document_id.

        Used before deleting Document to avoid FK constraint violations.

        Args:
            document_id: The document ID whose progress records should be deleted

        Returns:
            Number of records deleted
        """
        result = await self.session.execute(
            sql_delete(TaskProgress).where(TaskProgress.document_id == document_id)
        )
        await self.session.commit()
        return result.rowcount if hasattr(result, 'rowcount') else 0
