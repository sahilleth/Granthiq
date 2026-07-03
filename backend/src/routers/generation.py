from typing import Optional, Literal, Union, List
from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel, Field
from uuid import UUID
import os
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from src.config import get_settings
from src.services.generation.service import GenerationService, get_generation_service
from src.schemas.content import PodcastScript, Quiz, FlashcardDeck, MindMap
from src.services.auth import get_current_user
from src.db.session import get_session
from src.db.repositories.content import ContentRepository
from src.db.repositories.notebook import NotebookRepository
from src.db.repositories.task_progress import TaskProgressRepository
from src.db.models import ContentType, GeneratedContent, ProcessingStatus
from src.services.storage import get_storage_service
from src.schemas.pagination import (
    CursorPage,
    create_cursor_params,
    build_pagination_response,
)

# Procrastinate task queue (optional - use env var to enable)
USE_TASK_QUEUE = os.getenv("USE_TASK_QUEUE", "false").lower() == "true"

router = APIRouter(prefix="/generation", tags=["generation"])


class ContentItemResponse(BaseModel):
    """Response model for a single generated content item."""

    id: str
    notebook_id: str
    document_id: Optional[str] = None
    content_type: str
    status: str
    content: dict
    audio_url: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ContentListResponse(BaseModel):
    """Response model for list of generated content."""

    items: list[ContentItemResponse]
    total: int


@router.get(
    "/{notebook_id}/content",
    response_model=CursorPage[ContentItemResponse],
    summary="List generated content for a notebook",
)
async def list_content_endpoint(
    notebook_id: UUID,
    content_type: Optional[ContentType] = Query(
        None, description="Filter by content type"
    ),
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(
        default=20, ge=1, le=100, description="Number of items per page"
    ),
    cursor: Optional[str] = Query(default=None, description="Cursor for pagination"),
):
    """
    Get generated content for a notebook with pagination.
    Optionally filter by content_type (podcast, quiz, flashcard, mindmap).
    """
    notebook_repo = NotebookRepository(session)
    content_repo = ContentRepository(session)

    # Verify notebook ownership
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found or access denied",
        )

    # Get pagination params from cursor
    params = create_cursor_params(limit=limit, cursor=cursor, default_offset=0)
    offset = params["offset"]
    page_limit = params["limit"]

    # Get all content for counting
    all_content = await content_repo.get_by_notebook(notebook_id)
    total_count = len(all_content)

    # Filter by type if specified
    if content_type:
        all_content = [c for c in all_content if c.content_type == content_type]
        total_count = len(all_content)

    # Get paginated content
    paginated_content = await content_repo.get_by_notebook_paginated(
        notebook_id, limit=page_limit, offset=offset, content_type=content_type
    )

    # Convert to response format
    items = []
    storage_service = get_storage_service()

    for c in paginated_content:
        audio_url = c.audio_url

        # If podcast and has a key stored (not a full URL), generate signed URL
        if c.content_type == ContentType.PODCAST and audio_url:
            if not audio_url.startswith("http"):
                settings = get_settings()
                bucket_name = settings.storage.private_bucket
                audio_url = await storage_service.get_url(
                    audio_url, bucket_name, private=True
                )

        items.append(
            ContentItemResponse(
                id=str(c.id),
                notebook_id=str(c.notebook_id),
                document_id=str(c.document_id) if c.document_id else None,
                content_type=c.content_type.value,
                status=c.status.value,
                content=c.content or {},
                audio_url=audio_url,
                created_at=c.created_at.isoformat() if c.created_at else "",
                updated_at=c.updated_at.isoformat() if c.updated_at else "",
            )
        )

    # Build cursor-based pagination response
    return build_pagination_response(
        items=items,
        total_count=total_count,
        limit=page_limit,
        offset=offset,
        cursor_data={"sort_by": "created_at", "sort_order": "desc"},
    )


@router.get(
    "/{notebook_id}/content/{content_id}",
    response_model=ContentItemResponse,
    summary="Get a specific generated content item",
)
async def get_content_endpoint(
    notebook_id: UUID,
    content_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific generated content item by ID."""
    notebook_repo = NotebookRepository(session)
    content_repo = ContentRepository(session)

    # Verify notebook ownership
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found or access denied",
        )

    # Get content
    content = await content_repo.get(content_id)
    if not content or content.notebook_id != notebook_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Content not found"
        )

    return ContentItemResponse(
        id=str(content.id),
        notebook_id=str(content.notebook_id),
        document_id=str(content.document_id) if content.document_id else None,
        content_type=content.content_type.value,
        status=content.status.value,
        content=content.content or {},
        audio_url=content.audio_url,
        created_at=content.created_at.isoformat() if content.created_at else "",
        updated_at=content.updated_at.isoformat() if content.updated_at else "",
    )


class GenerateRequest(BaseModel):
    content_type: Literal["podcast", "quiz", "flashcard", "mindmap"]
    document_ids: Optional[List[UUID]] = (
        None  # If None, generates from all documents in notebook
    )


class AsyncGenerateResponse(BaseModel):
    """Response when using async task queue mode."""

    status: str = "queued"
    task_id: int
    content_id: UUID
    message: str


@router.post(
    "/{notebook_id}/generate",
    response_model=Union[
        PodcastScript, Quiz, FlashcardDeck, MindMap, AsyncGenerateResponse
    ],
    summary="Generate content",
)
async def generate_content_endpoint(
    notebook_id: UUID,
    request: GenerateRequest,
    async_mode: bool = Query(
        False, description="If true, queue task and return immediately"
    ),
    generation_service: GenerationService = Depends(get_generation_service),
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Generate content (podcast, quiz, flashcard, or mindmap) for a notebook.
    If document_ids is not provided, generates from all documents in the notebook.

    With async_mode=true (or USE_TASK_QUEUE=true env var), returns immediately with task_id.
    Poll /api/v1/tasks/{task_id} for progress.
    """
    # Verify notebook exists first
    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found or access denied",
        )

    # Async mode: queue task and return immediately
    if async_mode or USE_TASK_QUEUE:
        try:
            # Map content type to ContentType enum
            content_type_map = {
                "podcast": ContentType.PODCAST,
                "quiz": ContentType.QUIZ,
                "flashcard": ContentType.FLASHCARD,
                "mindmap": ContentType.MINDMAP,
            }

            # Create placeholder Content record with PENDING status
            content_repo = ContentRepository(session)
            saved_content = await content_repo.create_content(
                notebook_id=notebook_id,
                content_type=content_type_map[request.content_type],
                status=ProcessingStatus.PENDING,
            )

            # Queue appropriate task
            task_func = None
            if request.content_type == "podcast":
                from src.services.queue.tasks import generate_podcast_task

                task_func = generate_podcast_task
            elif request.content_type == "quiz":
                from src.services.queue.tasks import generate_quiz_task

                task_func = generate_quiz_task
            elif request.content_type == "flashcard":
                from src.services.queue.tasks import generate_flashcard_task

                task_func = generate_flashcard_task
            elif request.content_type == "mindmap":
                from src.services.queue.tasks import generate_mindmap_task

                task_func = generate_mindmap_task

            doc_ids = (
                [str(d) for d in request.document_ids] if request.document_ids else None
            )

            job = await task_func.defer_async(
                content_id=str(saved_content.id),
                notebook_id=str(notebook_id),
                user_id=str(user_id),
                document_ids=doc_ids,
            )

            # Handle both Job object (older procrastinate) and int (newer procrastinate) return types
            job_id = job.id if hasattr(job, "id") else job

            # Create task_progress record immediately so ownership checks work
            # This must happen BEFORE returning so the user can poll task status
            task_progress_repo = TaskProgressRepository(session)
            await task_progress_repo.create_progress(
                job_id=job_id,
                user_id=user_id,
                notebook_id=notebook_id,
                content_id=saved_content.id,
                progress_percent=0,
                message=f"{request.content_type.title()} generation queued",
            )
            logger.info(
                f"Created task_progress record for job_id={job_id}, user_id={user_id}"
            )

            logger.info(
                f"Content generation queued: {request.content_type} (job_id: {job_id})"
            )

            return AsyncGenerateResponse(
                status="queued",
                task_id=job_id,
                content_id=saved_content.id,
                message=f"{request.content_type.title()} generation queued. Poll /api/v1/tasks/{job_id} for progress.",
            )

        except Exception as e:
            logger.warning(
                f"Failed to queue generation task, falling back to sync: {e}"
            )
            # Fall through to synchronous mode

    # Synchronous mode (original behavior)
    result = await generation_service.generate_content(
        session=session,
        content_type=request.content_type,
        notebook_id=notebook_id,
        document_ids=request.document_ids,
        user_id=user_id,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to generate content. Please check input or try again.",
        )

    return result


@router.delete(
    "/{notebook_id}/content/{content_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete generated content",
)
async def delete_content_endpoint(
    notebook_id: UUID,
    content_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete a specific generated content item.
    Verifies ownership through notebook.
    """
    notebook_repo = NotebookRepository(session)
    content_repo = ContentRepository(session)

    # Verify notebook ownership
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found or access denied",
        )

    # Get content and verify it belongs to this notebook
    content = await content_repo.get(content_id)
    if not content or content.notebook_id != notebook_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Content not found"
        )

    # Delete related TaskProgress records first to avoid FK violation
    task_progress_repo = TaskProgressRepository(session)
    await task_progress_repo.delete_by_content_id(content_id)

    deleted = await content_repo.delete(content_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete content",
        )

    return None


@router.delete(
    "/{notebook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete all generated content for a notebook",
)
async def delete_notebook_content_endpoint(
    notebook_id: UUID,
    content_type: Optional[ContentType] = None,
    document_id: Optional[UUID] = None,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete generated content for a notebook.
    Optionally filter by content_type and/or document_id.
    If document_id is None, deletes notebook-level content.
    """
    notebook_repo = NotebookRepository(session)
    content_repo = ContentRepository(session)

    # Verify notebook ownership
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found or access denied",
        )

    if not content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="content_type is required"
        )

    deleted = await content_repo.delete_content(
        notebook_id=notebook_id, content_type=content_type, document_id=document_id
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No content found matching criteria",
        )

    return None


class CreateContentRequest(BaseModel):
    content_type: ContentType
    content: dict = Field(
        ..., max_length=100000, description="Content JSON (max 100KB)"
    )
    title: str = Field(..., min_length=1, max_length=500, description="Content title")
    status: str = "completed"


@router.post(
    "/{notebook_id}/content",
    response_model=ContentItemResponse,
    summary="Create generated content manually",
)
async def create_content_endpoint(
    notebook_id: UUID,
    request: CreateContentRequest,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Manually create a generated content item (e.g. for Notes).
    Does not trigger AI generation.
    """
    notebook_repo = NotebookRepository(session)
    content_repo = ContentRepository(session)

    # Verify notebook ownership
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found or access denied",
        )

    # Create content record
    # Inject title into content if not present
    content_data = request.content
    if isinstance(content_data, dict):
        content_data = content_data.copy()  # Avoid mutating original
        if "title" not in content_data:
            content_data["title"] = request.title

    content = await content_repo.create_content(
        notebook_id=notebook_id,
        content_type=request.content_type,
        status=ProcessingStatus(request.status),
        content=content_data,
    )

    return ContentItemResponse(
        id=str(content.id),
        notebook_id=str(content.notebook_id),
        document_id=None,
        content_type=content.content_type.value,
        status=content.status.value,
        content=content.content or {},
        audio_url=None,
        created_at=content.created_at.isoformat(),
        updated_at=content.updated_at.isoformat(),
    )
