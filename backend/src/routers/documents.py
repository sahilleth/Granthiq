from typing import List, Optional
from uuid import UUID
from pathlib import Path
import re
from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException,
    BackgroundTasks,
    Form,
    status,
    Request,
    Query,
)
from pydantic import BaseModel
import pydantic
from loguru import logger
import tempfile
import httpx
import os
from sqlmodel.ext.asyncio.session import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.db.session import get_session
from src.db.models import Document, ProcessingStatus
from src.db.repositories.document import DocumentRepository
from src.db.repositories.notebook import NotebookRepository
from src.db.repositories.task_progress import TaskProgressRepository
from src.services.storage import get_storage_service
from src.services.ingestion.main_processor import MainProcessor
from src.services.indexer.indexer import DocumentIndexer, get_indexer
from src.config import get_settings
from src.services.auth import get_current_user
from src.db.session import async_session_factory
from src.utils.security import sanitize_filename  # Security: prevent path traversal
from src.utils.url_validator import validate_url_for_ssrf
from src.schemas.pagination import (
    CursorPage,
    create_cursor_params,
    build_pagination_response,
)

# Procrastinate task queue (optional - use env var to enable)
USE_TASK_QUEUE = os.getenv("USE_TASK_QUEUE", "false").lower() == "true"


class ProcessUrlRequest(BaseModel):
    url: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=2048,
        description="URL to process (1-2048 characters)",
    )
    notebook_id: UUID


router = APIRouter(prefix="/documents", tags=["documents"])


async def schedule_document_processing(
    document_id: "UUID",
    user_id: "UUID",
    storage_path: str,
    bucket: str,
    notebook_id: "UUID",
    background_tasks: BackgroundTasks = None,
) -> int | None:
    """
    Schedule document processing using task queue or BackgroundTasks.

    Unified abstraction that:
    1. Tries task queue (Procrastinate) if enabled
    2. Falls back to FastAPI BackgroundTasks if queue fails or disabled

    Returns:
        Task ID if using task queue, None otherwise
    """
    task_id = None

    if USE_TASK_QUEUE:
        try:
            from src.services.queue.tasks import process_document_task

            job = await process_document_task.defer_async(
                document_id=str(document_id),
                user_id=str(user_id),
                storage_path=storage_path,
                file_path=None,  # Will be downloaded from storage
            )
            # Handle both job object (with .id) and int (direct job id)
            task_id = job.id if hasattr(job, "id") else job
            logger.info(
                f"Document {document_id} queued for processing (job_id: {task_id})"
            )
            return task_id
        except Exception as e:
            logger.warning(f"Task queue failed, falling back to BackgroundTasks: {e}")
            # Fall through to BackgroundTasks

    # Use FastAPI BackgroundTasks (fallback or legacy mode)
    if background_tasks:
        background_tasks.add_task(
            _process_document_task,
            document_id=document_id,
            storage_path=storage_path,
            bucket=bucket,
            notebook_id=notebook_id,
            user_id=user_id,
        )
        logger.info(f"Document {document_id} scheduled via BackgroundTasks")

    return task_id


# Initialize limiter for this router
limiter = Limiter(key_func=get_remote_address)


@router.post("/upload")
@limiter.limit("10/hour")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    notebook_id: UUID = Form(...),
    background_tasks: BackgroundTasks = None,
    session=Depends(get_session),
    user_id: UUID = Depends(get_current_user),
):
    """
    Upload a document (PDF, TXT, etc.) to Private Storage and start processing.
    """
    settings = get_settings()
    repo = DocumentRepository(session)
    storage = get_storage_service()

    # Check file size - use provider-specific limit
    max_size_mb = (
        settings.storage.max_file_size_mb
        if settings.storage.provider == "supabase"
        else settings.upload.max_size_mb
    )
    if file.size and file.size > max_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed: {max_size_mb}MB (Supabase free tier limit: 50MB per file)",
        )

    # Security: Sanitize filename to prevent path traversal attacks
    safe_filename = sanitize_filename(file.filename)
    logger.info(f"Sanitized filename: '{file.filename}' -> '{safe_filename}'")

    storage_path = f"{user_id}/{notebook_id}/document/{safe_filename}"
    bucket = settings.storage.private_bucket

    try:
        # Use streaming upload to avoid loading entire file into RAM
        # file.file is the underlying SpooledTemporaryFile
        await storage.upload_stream(
            file_obj=file.file,
            path=storage_path,
            bucket=bucket,
            mime_type=file.content_type or "application/octet-stream",
        )

        # Get file size for DB record (seek to end to get size, then reset)
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to start for potential reuse
    except Exception as e:
        logger.error(f"Storage upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file to storage")

    # 3. Verify notebook ownership
    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=403, detail="Notebook not found or access denied"
        )

    # 4. Create Database Record
    # We store the 'storage_path' (key) so we can generate signed URLs later
    doc = Document(
        notebook_id=notebook_id,
        filename=safe_filename,  # Use sanitized filename
        file_path=storage_path,
        mime_type=file.content_type or "application/octet-stream",
        status=ProcessingStatus.PENDING,
    )

    saved_doc = await repo.create(doc)

    # 5. Trigger Background Processing (unified abstraction)
    task_id = await schedule_document_processing(
        document_id=saved_doc.id,
        user_id=user_id,
        storage_path=storage_path,
        bucket=bucket,
        notebook_id=notebook_id,
        background_tasks=background_tasks,
    )

    response = {
        "status": "uploaded",
        "document_id": saved_doc.id,
        "filename": saved_doc.filename,
        "processing_status": saved_doc.status,
    }
    if task_id:
        response["task_id"] = task_id
    return response


@router.post("/url")
async def process_url(
    request: ProcessUrlRequest,
    background_tasks: BackgroundTasks,
    session=Depends(get_session),
    user_id: UUID = Depends(get_current_user),
):
    """Process a URL (Web or YouTube)."""
    # SSRF protection: block private IPs in production
    try:
        validate_url_for_ssrf(request.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo = DocumentRepository(session)

    # Check if notebook exists
    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(request.notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=403, detail="Notebook not found or access denied"
        )

    # Detect Type
    is_youtube = bool(re.search(r"(youtube\.com|youtu\.be)", request.url))
    mime_type = "video/youtube" if is_youtube else "text/html"

    # Create DB Record
    # Truncate filename to fit DB limit, full URL in file_path
    filename = request.url[:255]
    doc = Document(
        notebook_id=request.notebook_id,
        filename=filename,
        file_path=request.url,
        mime_type=mime_type,
        status=ProcessingStatus.PENDING,
    )
    saved_doc = await repo.create(doc)

    # Schedule Background Task
    background_tasks.add_task(
        _process_url_background_task,
        document_id=saved_doc.id,
        url=request.url,
        user_id=user_id,
        notebook_id=request.notebook_id,
        is_youtube=is_youtube,
    )

    return {
        "status": "pending",
        "document_id": saved_doc.id,
        "processing_status": saved_doc.status,
    }


@router.get("/{document_id}/url")
async def get_document_url(
    document_id: UUID,
    session=Depends(get_session),
    user_id: UUID = Depends(get_current_user),
):
    """
    Get a temporary Signed URL to view/download the document.
    Requires authentication and verifies notebook ownership.
    """
    repo = DocumentRepository(session)
    doc = await repo.get(document_id)

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify ownership through notebook
    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(doc.notebook_id, user_id)
    if not notebook:
        raise HTTPException(status_code=403, detail="Access denied")

    storage = get_storage_service()
    settings = get_settings()

    # Generate Signed URL (valid for 1 hour)
    url = await storage.get_url(
        path=doc.file_path, bucket=settings.storage.private_bucket, private=True
    )

    if not url:
        raise HTTPException(status_code=500, detail="Failed to generate access URL")

    return {"url": url, "expires_in": 3600}


@router.get("/notebook/{notebook_id}", response_model=CursorPage[Document])
async def list_documents(
    notebook_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(
        default=20, ge=1, le=100, description="Number of items per page"
    ),
    cursor: Optional[str] = Query(default=None, description="Cursor for pagination"),
):
    """
    Get all documents for a notebook with pagination.
    Returns documents ordered by creation date (newest first).
    """
    notebook_repo = NotebookRepository(session)
    repo = DocumentRepository(session)
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Get pagination params from cursor
    params = create_cursor_params(limit=limit, cursor=cursor, default_offset=0)
    offset = params["offset"]
    page_limit = params["limit"]

    # Get total count
    all_documents = await repo.get_by_notebook(notebook_id)
    total_count = len(all_documents)

    # Get paginated documents
    documents = await repo.get_by_notebook_paginated(
        notebook_id, limit=page_limit, offset=offset
    )

    # Build cursor-based pagination response
    return build_pagination_response(
        items=documents,
        total_count=total_count,
        limit=page_limit,
        offset=offset,
        cursor_data={"sort_by": "created_at", "sort_order": "desc"},
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a document."""
    doc_repo = DocumentRepository(session)
    doc = await doc_repo.get(document_id)

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify ownership through notebook
    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(doc.notebook_id, user_id)
    if not notebook:
        raise HTTPException(status_code=403, detail="Access denied")

    # Properly delete a document: remove from vector index, remove file from storage, delete DB record
    indexer = get_indexer()
    try:
        indexer.delete_document(document_id)
    except Exception as e:
        logger.warning(f"Failed to remove document {document_id} from index: {e}")

    storage = get_storage_service()
    settings = get_settings()
    try:
        storage.delete(doc.file_path, settings.storage.private_bucket)
    except Exception as e:
        logger.warning(f"Failed to delete file from storage at {doc.file_path}: {e}")

    # Delete associated task progress records first to avoid FK constraint violations
    task_progress_repo = TaskProgressRepository(session)
    try:
        deleted_count = await task_progress_repo.delete_by_document_id(document_id)
        if deleted_count > 0:
            logger.info(
                f"Deleted {deleted_count} task progress records for document {document_id}"
            )
    except Exception as e:
        logger.warning(
            f"Failed to delete task progress records for document {document_id}: {e}"
        )

    await doc_repo.delete(document_id)
    return None


async def _process_document_task(
    document_id: UUID, storage_path: str, bucket: str, notebook_id: UUID, user_id: UUID
):
    """
    Background task to download file from storage and run ingestion."""
    temp_file_path = None
    try:
        async with async_session_factory() as session:
            repo = DocumentRepository(session)
            storage = get_storage_service()
            # Get document to retrieve filename for temp file extension
            doc = await repo.get(document_id)
            if not doc:
                logger.error(f"Document not found: {document_id}")
                try:
                    await repo.update_status(
                        document_id, ProcessingStatus.FAILED, "Document not found"
                    )
                except Exception as status_error:
                    logger.warning(f"Failed to update document status: {status_error}")
                return

            # Fetch notebook to apply custom chunking settings
            notebook_repo = NotebookRepository(session)
            notebook = await notebook_repo.get(notebook_id)

            chunk_size = None
            chunk_overlap = None
            if notebook and notebook.settings:
                chunk_size = notebook.settings.get("chunk_size")
                chunk_overlap = notebook.settings.get("chunk_overlap")
                logger.info(
                    f"Using notebook settings for processing: chunk_size={chunk_size}, overlap={chunk_overlap}"
                )

            processor = MainProcessor(
                chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )

            try:
                # 1. Get Signed URL to download file
                file_url = await storage.get_url(storage_path, bucket, private=True)
                if not file_url:
                    raise Exception(
                        "Could not generate download URL for processing. Make sure the storage bucket exists."
                    )

                # 2. Download file to temp location
                file_extension = Path(doc.filename).suffix
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=file_extension
                ) as temp_file:
                    async with httpx.AsyncClient() as client:
                        async with client.stream("GET", file_url) as response:
                            response.raise_for_status()
                            async for chunk in response.aiter_bytes():
                                temp_file.write(chunk)
                    temp_file_path = temp_file.name

                # 3. Process file - MainProcessor handles all status updates internally
                # Pass user_id so UnifiedDocument has it for vector store metadata
                # Pass original_filename so citations show real name, not temp file name
                processed_doc = await processor.process_file(
                    file_path=temp_file_path,
                    user_id=user_id,
                    storage_path=storage_path,
                    source_id=document_id,
                    auto_chunk=True,
                    original_filename=doc.filename,
                )

                # 4. Add notebook_id to metadata for filtering support
                if notebook_id and processed_doc.metadata:
                    processed_doc.metadata["notebook_id"] = str(notebook_id)

                # 5. Index the document in vector store
                indexer = get_indexer()
                try:
                    node_ids = indexer.index_document(
                        processed_doc, replace_existing=True
                    )
                    logger.info(
                        f"Indexed doc {document_id}: {len(node_ids)} nodes created"
                    )
                except Exception as index_error:
                    logger.error(
                        f"Indexing failed for doc {document_id}: {index_error}",
                        exc_info=True,
                    )
                    # Don't fail the whole process if indexing fails - document is still processed

                logger.info(
                    f"Successfully processed doc {document_id}: {processed_doc.chunk_count} chunks"
                )

            except Exception as e:
                logger.error(
                    f"Processing failed for doc {document_id}: {e}", exc_info=True
                )
                # Only update status if MainProcessor didn't already (e.g., if download failed before process_file was called)
                # MainProcessor will handle status updates if process_file was called
                try:
                    current_doc = await repo.get(document_id)
                    if current_doc and current_doc.status != ProcessingStatus.FAILED:
                        await repo.update_status(
                            document_id, ProcessingStatus.FAILED, str(e)
                        )
                except Exception as update_error:
                    logger.error(f"Failed to update status after error: {update_error}")
            finally:
                # Cleanup temp file
                if temp_file_path and Path(temp_file_path).exists():
                    try:
                        Path(temp_file_path).unlink(missing_ok=True)
                    except Exception as cleanup_error:
                        logger.warning(
                            f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}"
                        )

    except Exception as session_error:
        # Handle database connection errors during session cleanup
        # This can happen if the connection is closed while the background task is still running
        # Since processing already completed successfully, these errors are harmless
        error_str = str(session_error).lower()
        if (
            "connection" in error_str
            or "closed" in error_str
            or "does not exist" in error_str
        ):
            # Silently ignore connection cleanup errors - they're harmless and expected
            # The document processing completed successfully before the connection closed
            pass  # Don't log - it's expected behavior in background tasks
        else:
            logger.error(
                f"Unexpected error in background task for doc {document_id}: {session_error}",
                exc_info=True,
            )


async def _process_url_background_task(
    document_id: UUID, url: str, user_id: UUID, notebook_id: UUID, is_youtube: bool
):
    """Background task to process URL."""
    try:
        async with async_session_factory() as session:
            repo = DocumentRepository(session)

            # Fetch notebook for settings
            notebook_repo = NotebookRepository(session)
            notebook = await notebook_repo.get(notebook_id)

            chunk_size = None
            chunk_overlap = None
            if notebook and notebook.settings:
                chunk_size = notebook.settings.get("chunk_size")
                chunk_overlap = notebook.settings.get("chunk_overlap")

            processor = MainProcessor(
                chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )

            try:
                # Process
                if is_youtube:
                    unified_doc = await processor.process_youtube(
                        url, user_id=user_id, source_id=document_id
                    )
                else:
                    unified_doc = await processor.process_url(
                        url, user_id=user_id, source_id=document_id
                    )

                # Update filename if better title found
                if unified_doc.filename and unified_doc.filename != url:
                    # Ensure we don't exceed column size
                    new_filename = unified_doc.filename[:255]
                    await repo.update(document_id, {"filename": new_filename})

                # Add notebook_id to metadata
                if notebook_id and unified_doc.metadata:
                    unified_doc.metadata["notebook_id"] = str(notebook_id)

                # Index
                indexer = get_indexer()
                try:
                    await indexer.index_document(unified_doc, replace_existing=True)
                    logger.info(f"Indexed URL doc {document_id}")
                except Exception as index_error:
                    logger.error(
                        f"Indexing failed for URL doc {document_id}: {index_error}",
                        exc_info=True,
                    )

            except Exception as e:
                logger.error(
                    f"Processing failed for URL {document_id}: {e}", exc_info=True
                )
                # Ensure status is updated to FAILED (MainProcessor usually handles this, but just in case)
                try:
                    current_doc = await repo.get(document_id)
                    if current_doc and current_doc.status != ProcessingStatus.FAILED:
                        await repo.update_status(
                            document_id, ProcessingStatus.FAILED, str(e)
                        )
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Critical error in URL background task: {e}", exc_info=True)
