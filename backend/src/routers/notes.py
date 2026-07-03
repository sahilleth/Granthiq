from typing import List, Optional
from uuid import UUID
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from src.db.session import get_session, async_session_factory
from src.db.models import Document, ProcessingStatus
from src.db.repositories.document import DocumentRepository
from src.db.repositories.notebook import NotebookRepository
from src.services.auth import get_current_user
from src.services.indexer.indexer import get_indexer
from src.schemas.document import UnifiedDocument, DocumentChunk, DocumentType


router = APIRouter(prefix="/notes", tags=["notes"])


# === Request/Response Models ===


class NoteBase(BaseModel):
    """Base note model with common fields."""

    title: str = Field(default="Untitled Note", min_length=1, max_length=500)
    content: str = Field(
        default="",
        min_length=0,
        max_length=50000,
        description="HTML or plain text content of the note",
    )


class CreateNoteRequest(NoteBase):
    """Request model for creating a new note."""

    notebook_id: UUID


class UpdateNoteRequest(BaseModel):
    """Request model for updating a note."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = Field(None, min_length=0, max_length=50000)


class NoteResponse(BaseModel):
    """Response model for a note."""

    id: str
    notebook_id: str
    title: str
    content: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ConvertToSourceRequest(BaseModel):
    """Request model for converting a note to a source."""

    note_id: str = Field(..., description="The ID of the note to convert")
    title: str = Field(..., max_length=500, description="Title of the note")
    content: str = Field(..., min_length=1, description="Content of the note to index")
    notebook_id: UUID = Field(..., description="The notebook to add the source to")


class ConvertToSourceResponse(BaseModel):
    """Response model for the convert-to-source operation."""

    success: bool
    document_id: str
    message: str
    status: str = "pending"  # pending, processing, completed, failed


# === Background Task ===


async def _index_note_as_source(
    document_id: UUID, notebook_id: UUID, user_id: UUID, title: str, content: str
):
    """
    Background task to index a note as a searchable source.

    This task:
    1. Creates a UnifiedDocument from the note content
    2. Chunks the content appropriately
    3. Indexes the chunks in the vector store
    4. Updates the document status to COMPLETED or FAILED
    """
    async with async_session_factory() as session:
        doc_repo = DocumentRepository(session)

        try:
            # Update status to PROCESSING
            await doc_repo.update_status(document_id, ProcessingStatus.PROCESSING)
            await session.commit()

            # Strip HTML tags for plain text indexing (basic approach)
            import re

            plain_content = re.sub(r"<[^>]+>", " ", content)
            plain_content = re.sub(r"\s+", " ", plain_content).strip()

            # Fallback: if stripping resulted in empty string (e.g. only tags), use original
            if not plain_content:
                logger.warning(
                    f"Note {document_id} content empty after stripping tags. Using original content."
                )
                plain_content = content.strip()

            if not plain_content:
                raise ValueError("Note content is empty")

            # Create UnifiedDocument for indexing
            unified_doc = UnifiedDocument(
                id=document_id,
                user_id=user_id,
                filename=f"{title}.note",
                source_type=DocumentType.TXT,
                status="COMPLETED",
                storage_path=f"notes/{document_id}",  # Virtual path for notes
                metadata={
                    "notebook_id": str(notebook_id),
                    "source_type": "note",
                    "title": title,
                    "original_content_type": "note",
                },
            )

            # Chunk the content
            # For notes, we use smaller chunks since they're typically shorter
            chunk_size = 500
            chunk_overlap = 50

            # Simple chunking by splitting into sentences/paragraphs
            # and then grouping into appropriate chunk sizes
            sentences = re.split(r"(?<=[.!?])\s+", plain_content)

            current_chunk = []
            current_length = 0
            chunk_index = 0

            for sentence in sentences:
                sentence_length = len(sentence)

                if current_length + sentence_length > chunk_size and current_chunk:
                    # Save current chunk
                    chunk_text = " ".join(current_chunk)
                    unified_doc.add_chunk(
                        content=chunk_text,
                        chunk_index=chunk_index,
                        metadata={"title": title},
                    )
                    chunk_index += 1

                    # Start new chunk with overlap (keep last sentence)
                    if chunk_overlap > 0 and current_chunk:
                        overlap_text = (
                            current_chunk[-1]
                            if len(current_chunk[-1]) <= chunk_overlap
                            else ""
                        )
                        current_chunk = [overlap_text] if overlap_text else []
                        current_length = len(overlap_text)
                    else:
                        current_chunk = []
                        current_length = 0

                current_chunk.append(sentence)
                current_length += sentence_length + 1  # +1 for space

            # Don't forget the last chunk
            if current_chunk:
                chunk_text = " ".join(current_chunk)
                unified_doc.add_chunk(
                    content=chunk_text,
                    chunk_index=chunk_index,
                    metadata={"title": title},
                )

            # If no chunks were created (very short content), create a single chunk
            if not unified_doc.chunks:
                unified_doc.add_chunk(
                    content=plain_content, chunk_index=0, metadata={"title": title}
                )

            # Index the document
            indexer = get_indexer()
            node_ids = await indexer.index_document(unified_doc, replace_existing=True)

            logger.info(
                f"Indexed note {document_id} as source: {len(node_ids)} nodes created"
            )

            # Update document with chunk count and status
            await doc_repo.update(
                document_id,
                {
                    "status": ProcessingStatus.COMPLETED,
                    "chunk_count": len(unified_doc.chunks),
                },
            )
            await session.commit()

        except Exception as e:
            logger.error(f"Failed to index note {document_id}: {e}", exc_info=True)

            try:
                await doc_repo.update_status(
                    document_id, ProcessingStatus.FAILED, error_message=str(e)[:500]
                )
                await session.commit()
            except Exception as update_error:
                logger.error(f"Failed to update error status: {update_error}")


# === API Endpoints ===


@router.post(
    "/convert-to-source",
    response_model=ConvertToSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Convert a note to a searchable source",
)
async def convert_note_to_source(
    request: ConvertToSourceRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    user_id: UUID = Depends(get_current_user),
):
    """
    Convert a note into a searchable source (document).

    This endpoint:
    1. Validates the notebook ownership
    2. Creates a Document record for the note
    3. Schedules background indexing for RAG retrieval
    4. Returns immediately with the document ID

    The client should delete the note from local storage after receiving
    a successful response.

    Edge cases handled:
    - Empty content: Returns 400 Bad Request
    - Notebook not found/access denied: Returns 404
    - Already converted (duplicate): Creates a new version
    """
    # Validate content is not empty
    content = request.content.strip()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot convert empty note to source",
        )

    # Verify notebook ownership
    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(request.notebook_id, user_id)

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found or access denied",
        )

    # Create Document record
    doc_repo = DocumentRepository(session)

    # Generate a safe filename from the title
    safe_title = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "_" for c in request.title
    )
    safe_title = safe_title[:100]  # Limit length
    filename = f"{safe_title}.note"

    # Create the document record
    document = Document(
        notebook_id=request.notebook_id,
        filename=filename,
        file_path=f"notes/{user_id}/{request.notebook_id}/{request.note_id}",  # Virtual path
        mime_type="text/plain",  # Notes are treated as plain text
        status=ProcessingStatus.PENDING,
        chunk_count=0,
    )

    saved_document = await doc_repo.create(document)

    logger.info(
        f"Created document {saved_document.id} from note {request.note_id} for user {user_id}"
    )

    # Schedule background indexing
    background_tasks.add_task(
        _index_note_as_source,
        document_id=saved_document.id,
        notebook_id=request.notebook_id,
        user_id=user_id,
        title=request.title,
        content=content,
    )

    return ConvertToSourceResponse(
        success=True,
        document_id=str(saved_document.id),
        message="Note is being converted to source. It will appear in your sources list shortly.",
        status="pending",
    )


@router.get(
    "/convert-status/{document_id}",
    response_model=ConvertToSourceResponse,
    summary="Check the status of a note-to-source conversion",
)
async def get_conversion_status(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
    user_id: UUID = Depends(get_current_user),
):
    """
    Check the status of a note-to-source conversion.

    This endpoint allows the frontend to poll for completion status
    after initiating a conversion.
    """
    doc_repo = DocumentRepository(session)
    document = await doc_repo.get(document_id)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    # Verify ownership through notebook
    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(document.notebook_id, user_id)

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    status_messages = {
        ProcessingStatus.PENDING: "Conversion queued, waiting to start...",
        ProcessingStatus.PROCESSING: "Converting note to searchable source...",
        ProcessingStatus.COMPLETED: "Note successfully converted to source!",
        ProcessingStatus.FAILED: f"Conversion failed: {document.error_message or 'Unknown error'}",
    }

    return ConvertToSourceResponse(
        success=document.status == ProcessingStatus.COMPLETED,
        document_id=str(document.id),
        message=status_messages.get(document.status, "Unknown status"),
        status=document.status.value.lower(),
    )
