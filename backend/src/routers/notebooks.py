from typing import List, Optional, Any, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, status, Query
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from src.db.session import get_session
from src.db.repositories.notebook import NotebookRepository
from src.db.repositories.document import DocumentRepository
from src.db.models import Notebook
from src.services.auth import get_current_user
from src.schemas.rag_config import NotebookRAGConfig
from src.schemas.pagination import (
    CursorPage,
    PaginationParams,
    create_cursor_params,
    build_pagination_response,
)
from src.schemas.error import ErrorCode
from src.utils.errors import AppHTTPException
from datetime import datetime, timezone
from loguru import logger

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


class NotebookCreate(BaseModel):
    title: str = Field(
        default="Untitled Notebook",
        min_length=1,
        max_length=255,
        description="Notebook title (1-255 characters)",
    )
    settings: Optional[NotebookRAGConfig] = None


class NotebookUpdate(BaseModel):
    title: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Notebook title (1-255 characters)",
    )
    settings: Optional[NotebookRAGConfig] = None


class NotebookWithSources(BaseModel):
    """Notebook response with source count for homepage display."""

    id: UUID
    user_id: UUID
    title: str
    settings: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime
    source_count: int = 0

    class Config:
        from_attributes = True


@router.get("", response_model=CursorPage[NotebookWithSources])
async def list_notebooks(
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(
        default=20, ge=1, le=100, description="Number of items per page"
    ),
    cursor: Optional[str] = Query(default=None, description="Cursor for pagination"),
):
    """
    Get notebooks for the current user with source counts.
    Returns paginated notebooks ordered by most recently updated.

    Use the `next_cursor` from response to fetch the next page.
    """
    logger.info(
        f"list_notebooks called, user_id={user_id}, limit={limit}, cursor={cursor[:20] + '...' if cursor and len(cursor) > 20 else cursor}"
    )

    notebook_repo = NotebookRepository(session)
    document_repo = DocumentRepository(session)

    # Get pagination params from cursor
    params = create_cursor_params(limit=limit, cursor=cursor, default_offset=0)
    offset = params["offset"]
    page_limit = params["limit"]

    # Get total count
    total_count = await notebook_repo.count_user_notebooks(user_id)

    # Get notebooks with pagination
    notebooks = await notebook_repo.get_user_notebooks_paginated(
        user_id=user_id, limit=page_limit, offset=offset
    )

    # Build response with source counts
    items = []
    for notebook in notebooks:
        source_count = await document_repo.count({"notebook_id": notebook.id})
        items.append(
            NotebookWithSources(
                id=notebook.id,
                user_id=notebook.user_id,
                title=notebook.title,
                settings=notebook.settings or {},
                created_at=notebook.created_at,
                updated_at=notebook.updated_at,
                source_count=source_count,
            )
        )

    # Build cursor-based pagination response
    return build_pagination_response(
        items=items,
        total_count=total_count,
        limit=page_limit,
        offset=offset,
        cursor_data={"sort_by": "updated_at", "sort_order": "desc"},
    )


@router.post("", response_model=Notebook, status_code=status.HTTP_201_CREATED)
async def create_notebook(
    data: NotebookCreate,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new notebook for the current user.
    """
    repo = NotebookRepository(session)
    notebook = await repo.create_notebook(user_id, data.title)

    # Update settings if provided
    if data.settings:
        # Convert Pydantic model to dict (exclude None values)
        settings_dict = data.settings.model_dump(exclude_none=True)
        await repo.update_settings(notebook.id, settings_dict)
        # Refresh to get updated settings
        notebook = await repo.get(notebook.id)

    # Schedule auto-rename task (3 minutes delay)
    try:
        from src.services.queue.tasks import auto_rename_notebook_task

        await auto_rename_notebook_task.defer_async(
            notebook_id=str(notebook.id), user_id=str(user_id), delay=180
        )
    except Exception as e:
        # Don't fail creation if scheduling fails
        logger.warning(f"Failed to schedule auto-rename: {e}")

    return notebook


@router.get("/{notebook_id}", response_model=Notebook)
async def get_notebook(
    notebook_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Get a specific notebook by ID.
    Verifies ownership before returning.
    """
    repo = NotebookRepository(session)
    notebook = await repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOTEBOOK_NOT_FOUND,
            message="Notebook not found or access denied",
            field="notebook_id",
        )
    return notebook


@router.patch("/{notebook_id}", response_model=Notebook)
async def update_notebook(
    notebook_id: UUID,
    data: NotebookUpdate,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Update notebook title or settings.
    Verifies ownership before updating.
    """
    repo = NotebookRepository(session)
    notebook = await repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOTEBOOK_NOT_FOUND,
            message="Notebook not found or access denied",
            field="notebook_id",
        )

    update_data = {}
    if data.title is not None:
        update_data["title"] = data.title
    if data.settings is not None:
        # Convert Pydantic model to dict (exclude None values)
        settings_dict = data.settings.model_dump(exclude_none=True)
        # Merge with existing settings
        current_settings = (notebook.settings or {}).copy()
        current_settings.update(settings_dict)
        update_data["settings"] = current_settings
        await repo.update_settings(notebook_id, current_settings)
    else:
        # Only update title
        if update_data:
            # Always update updated_at when modifying notebook
            update_data["updated_at"] = datetime.now(timezone.utc)
            await repo.update(notebook_id, update_data)

    # Return updated notebook
    updated_notebook = await repo.get(notebook_id)
    return updated_notebook


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(
    notebook_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete a notebook and all its related data (cascade delete).
    Verifies ownership before deletion.
    """
    repo = NotebookRepository(session)
    deleted = await repo.delete_notebook(notebook_id, user_id)
    if not deleted:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOTEBOOK_NOT_FOUND,
            message="Notebook not found or access denied",
            field="notebook_id",
        )
    return None
