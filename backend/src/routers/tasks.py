
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Any
from uuid import UUID
from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from src.db.session import get_session
from src.services.auth import get_current_user
from src.services.queue.app import proc_app


router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskStatusResponse(BaseModel):
    """Response model for task status."""
    
    job_id: int
    status: str  # todo, doing, succeeded, failed, cancelled, aborted
    queue_name: str
    task_name: str
    attempts: int
    scheduled_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Any] = None


class TaskDeferResponse(BaseModel):
    """Response when a task is deferred."""

    job_id: int
    status: str = "queued"
    message: str


async def verify_task_ownership(
    session: AsyncSession,
    job_id: int,
    user_id: UUID
) -> bool:
    """
    Verify that a task belongs to the specified user.

    Checks task_progress table for user_id match, or falls back to
    checking related document/content ownership.

    Returns:
        True if user owns the task, False otherwise
    """
    from sqlalchemy import text

    # First, check task_progress table for direct user_id match
    result = await session.execute(
        text("""
            SELECT user_id FROM task_progress
            WHERE job_id = :job_id
            LIMIT 1
        """),
        {"job_id": job_id}
    )
    row = result.fetchone()

    if row and row.user_id:
        return str(row.user_id) == str(user_id)

    # If no task_progress entry, check via document/content ownership
    # This handles cases where progress hasn't been written yet
    result = await session.execute(
        text("""
            SELECT tp.document_id, tp.content_id
            FROM task_progress tp
            WHERE tp.job_id = :job_id
            LIMIT 1
        """),
        {"job_id": job_id}
    )
    row = result.fetchone()

    if row:
        # Check document ownership
        if row.document_id:
            doc_result = await session.execute(
                text("""
                    SELECT 1 FROM document d
                    JOIN notebook n ON d.notebook_id = n.id
                    WHERE d.id = :doc_id AND n.user_id = :user_id
                """),
                {"doc_id": row.document_id, "user_id": str(user_id)}
            )
            if doc_result.fetchone():
                return True

        # Check content ownership
        if row.content_id:
            content_result = await session.execute(
                text("""
                    SELECT 1 FROM generatedcontent gc
                    JOIN notebook n ON gc.notebook_id = n.id
                    WHERE gc.id = :content_id AND n.user_id = :user_id
                """),
                {"content_id": row.content_id, "user_id": str(user_id)}
            )
            if content_result.fetchone():
                return True

    # If we can't verify ownership, deny access (fail secure)
    return False


@router.get("/{job_id}", response_model=TaskStatusResponse)
async def get_task_status(
    job_id: int,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Get the status of a background task.

    Args:
        job_id: The Procrastinate job ID

    Returns:
        TaskStatusResponse with current status, attempts, and any result/error

    Raises:
        403: If user doesn't own the task
        404: If task not found
    """
    try:
        from sqlalchemy import text

        # Verify ownership first
        if not await verify_task_ownership(session, job_id, user_id):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to view this task"
            )

        # Query procrastinate_jobs table directly
        result = await session.execute(
            text("""
                SELECT
                    id,
                    queue_name,
                    task_name,
                    status::text,
                    attempts,
                    scheduled_at,
                    args
                FROM procrastinate_jobs
                WHERE id = :job_id
            """),
            {"job_id": job_id}
        )

        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Task {job_id} not found")

        return TaskStatusResponse(
            job_id=row.id,
            queue_name=row.queue_name,
            task_name=row.task_name,
            status=row.status,
            attempts=row.attempts,
            scheduled_at=row.scheduled_at.isoformat() if row.scheduled_at else None,
            result=None,  # Result is in args, but typically stored separately
            error=None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get task status for job_id={}: {}: {}", job_id, type(e).__name__, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve task status: {str(e)}")


@router.get("/{job_id}/progress")
async def get_task_progress(
    job_id: int,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Get the progress of a background task.

    Args:
        job_id: The Procrastinate job ID

    Returns:
        Progress information including percentage and message

    Raises:
        403: If user doesn't own the task
    """
    try:
        from sqlalchemy import text

        # Verify ownership first
        if not await verify_task_ownership(session, job_id, user_id):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to view this task"
            )

        result = await session.execute(
            text("""
                SELECT
                    progress_percent,
                    message,
                    document_id,
                    content_id,
                    updated_at
                FROM task_progress
                WHERE job_id = :job_id
                ORDER BY updated_at DESC
                LIMIT 1
            """),
            {"job_id": job_id}
        )

        row = result.fetchone()

        if not row:
            # No progress yet, return default
            return {
                "job_id": job_id,
                "progress_percent": 0,
                "message": "Task queued",
                "document_id": None,
                "content_id": None
            }

        return {
            "job_id": job_id,
            "progress_percent": row.progress_percent,
            "message": row.message,
            "document_id": str(row.document_id) if row.document_id else None,
            "content_id": str(row.content_id) if row.content_id else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get task progress: {}", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve task progress")


@router.post("/{job_id}/cancel")
async def cancel_task(
    job_id: int,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Request cancellation of a background task.

    Note: This sets abort_requested=true. The worker will check this
    and abort the task at the next opportunity.

    Args:
        job_id: The Procrastinate job ID

    Returns:
        Cancellation status

    Raises:
        403: If user doesn't own the task
        404: If task not found or already completed
    """
    try:
        from sqlalchemy import text

        # Verify ownership first
        if not await verify_task_ownership(session, job_id, user_id):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to cancel this task"
            )

        # Set abort_requested flag
        result = await session.execute(
            text("""
                UPDATE procrastinate_jobs
                SET abort_requested = true
                WHERE id = :job_id AND status IN ('todo', 'doing')
                RETURNING id
            """),
            {"job_id": job_id}
        )

        row = result.fetchone()
        await session.commit()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Task {job_id} not found or already completed"
            )

        logger.info(f"Cancellation requested for task {job_id} by user {user_id}")

        return {
            "job_id": job_id,
            "status": "cancellation_requested",
            "message": "Abort flag set. Task will be cancelled at next checkpoint."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to cancel task: {}", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to cancel task")
