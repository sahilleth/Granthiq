import asyncio
from typing import List, Optional, Literal, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from loguru import logger
from src.db.session import get_session, async_session_factory
from src.db.repositories.notebook import NotebookRepository
from src.db.models import ChatMessage
from src.services.auth import get_current_user
from src.services.chat.service import ChatService
from src.dependencies import get_chat_service
from src.schemas.pagination import (
    CursorPage,
    create_cursor_params,
    build_pagination_response,
)

router = APIRouter(prefix="/chat", tags=["chat"])


limiter = Limiter(key_func=get_remote_address)


# === Response Schemas ===


class CitationResponse(BaseModel):
    """Citation with document filename for frontend display."""

    id: str
    message_id: str
    document_id: str
    filename: Optional[str] = None
    text_preview: str
    score: float
    page_number: Optional[int] = None


class ChatMessageResponse(BaseModel):
    """Chat message with properly serialized citations."""

    id: str
    notebook_id: str
    role: str
    content: str
    created_at: datetime
    citations: List[CitationResponse] = []
    confidence: Optional[Dict[str, Any]] = None


class ChatMessageRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Chat message (1-10000 characters)",
    )
    stream: bool = False
    mode: Literal["chat", "research"] = Field(
        default="chat",
        description="'chat' for standard RAG, 'research' for multi-step research agent",
    )


class SuggestedQuestion(BaseModel):
    """A single suggested question with context."""

    id: str
    text: str
    context: Optional[str] = Field(
        None, description="Source context, e.g., 'Based on: document.pdf'"
    )


class SuggestionsResponse(BaseModel):
    """Response for suggested questions endpoint."""

    questions: List[SuggestedQuestion]
    generated_at: str
    document_count: int


@router.get("/{notebook_id}/suggestions", response_model=SuggestionsResponse)
@limiter.limit("10/minute")
async def get_suggestions(
    request: Request,
    notebook_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Generate contextual suggested questions based on notebook content.

    Uses LLM to analyze document summaries and generate relevant questions.
    Results are cached for 5 minutes via Cache-Control headers.
    """

    # Verify notebook ownership
    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=404, detail="Notebook not found or access denied"
        )

    chat_service = get_chat_service()

    try:
        result = await chat_service.generate_suggestions(
            session=session, notebook_id=notebook_id, user_id=user_id
        )

        # Return with cache headers (5 minutes)
        response = JSONResponse(content=result)
        response.headers["Cache-Control"] = "private, max-age=300"
        return response

    except Exception as e:
        logger.error(f"Failed to generate suggestions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate suggestions")


class PromptEnhanceRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class PromptEnhanceResponse(BaseModel):
    enhanced_message: str


@router.post("/{notebook_id}/enhance_prompt", response_model=PromptEnhanceResponse)
@limiter.limit("20/minute")
async def enhance_prompt_text(
    request: Request,
    notebook_id: UUID,
    body: PromptEnhanceRequest,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Enhance a user prompt for better LLM results.
    """

    # Verify notebook access
    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    chat_service = get_chat_service()
    try:
        enhanced = await chat_service.enhance_prompt(body.message)
        return {"enhanced_message": enhanced}
    except Exception as e:
        logger.error(f"Failed to enhance prompt: {e}")
        return {"enhanced_message": body.message}


class SuggestionRequest(BaseModel):
    last_user_message: str = Field(
        ..., min_length=1, max_length=5000, description="The last user message"
    )
    last_assistant_message: str = Field(
        ..., min_length=1, max_length=10000, description="The last assistant response"
    )


class SuggestionResponse(BaseModel):
    questions: List[str]


@router.post("/{notebook_id}/suggestions", response_model=SuggestionResponse)
@limiter.limit("20/minute")
async def get_chat_suggestions(
    request: Request,
    notebook_id: UUID,
    body: SuggestionRequest,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Generate follow-up question suggestions based on the last conversation turn.
    Call this from frontend 'onFinish' of the chat stream.
    """

    # Verify notebook ownership
    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=404, detail="Notebook not found or access denied"
        )

    chat_service = get_chat_service()

    try:
        questions = await chat_service.generate_conversation_suggestions(
            user_message=body.last_user_message,
            assistant_message=body.last_assistant_message,
        )

        return {"questions": questions}

    except Exception as e:
        logger.error(f"Failed to generate conversation suggestions: {e}", exc_info=True)
        return {"questions": []}


@router.post("/{notebook_id}/message")
@limiter.limit("20/minute")
async def send_message(
    request: Request,
    notebook_id: UUID,
    body: ChatMessageRequest,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Send a message and get a response.
    Supports both streaming and non-streaming responses.
    """

    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=404, detail="Notebook not found or access denied"
        )

    chat_service = get_chat_service()

    try:
        if body.stream:

            async def generate():
                import json

                # Use a dedicated session scoped to the stream's lifetime instead of the
                # request-scoped `session` (Depends(get_session)). A StreamingResponse keeps
                # running long after the endpoint returns, so reusing the request session
                # holds its DB connection for the entire LLM generation and orphans it (leak)
                # if the client disconnects mid-stream. `async with` guarantees the connection
                # is returned to the pool even on cancellation.
                async with async_session_factory() as stream_session:
                    try:
                        generator = await chat_service.send_message(
                            session=stream_session,
                            notebook_id=notebook_id,
                            user_id=user_id,
                            message=body.message,
                            stream=True,
                            mode=body.mode,
                        )
                        async for token in generator:
                            # Check if it's already JSON (citations payload)
                            if token.startswith("{"):
                                yield f"data: {token}\n\n"
                            else:
                                # JSON-encode text tokens to preserve newlines and special chars
                                yield f"data: {json.dumps(token)}\n\n"
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.error(f"Stream generation error: {e}", exc_info=True)
                        yield f"data: {json.dumps({'type': 'error', 'error': 'An error occurred generating the response'})}\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")
        else:
            result = await chat_service.send_message(
                session=session,
                notebook_id=notebook_id,
                user_id=user_id,
                message=body.message,
                stream=False,
                mode=body.mode,
            )
            return result

    except HTTPException:
        raise
    except Exception as e:
        # Log internal details, return generic message to user (security best practice)
        logger.error(f"Chat processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="An error occurred processing your message"
        )


@router.get("/{notebook_id}/history", response_model=CursorPage[ChatMessageResponse])
async def get_history(
    notebook_id: UUID,
    limit: int = Query(
        default=50, ge=1, le=100, description="Number of messages per page"
    ),
    cursor: Optional[str] = Query(default=None, description="Cursor for pagination"),
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Get chat history for a notebook with pagination.
    Returns messages in chronological order (oldest first) with citations.
    """
    # Verify notebook ownership
    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=404, detail="Notebook not found or access denied"
        )

    # Get pagination params from cursor
    params = create_cursor_params(limit=limit, cursor=cursor, default_offset=0)
    offset = params["offset"]
    page_limit = params["limit"]

    chat_service = get_chat_service()

    # Get total count
    total_count = await chat_service.get_history_count(session, notebook_id)

    # Get paginated messages
    messages = await chat_service.get_history(
        session, notebook_id, limit=page_limit, offset=offset
    )

    # Serialize messages with citations including document filenames
    items = []
    for msg in messages:
        citations = []
        for cit in msg.citations:
            filename = None
            if cit.document:
                filename = cit.document.filename

            citations.append(
                CitationResponse(
                    id=str(cit.id),
                    message_id=str(cit.message_id),
                    document_id=str(cit.document_id),
                    filename=filename,
                    text_preview=cit.text_preview,
                    score=cit.score,
                    page_number=cit.page_number,
                )
            )

        items.append(
            ChatMessageResponse(
                id=str(msg.id),
                notebook_id=str(msg.notebook_id),
                role=msg.role.value if hasattr(msg.role, "value") else str(msg.role),
                content=msg.content,
                created_at=msg.created_at,
                citations=citations,
                confidence=msg.confidence,
            )
        )

    # Build cursor-based pagination response
    return build_pagination_response(
        items=items,
        total_count=total_count,
        limit=page_limit,
        offset=offset,
        cursor_data={"sort_by": "created_at", "sort_order": "asc"},
    )


@router.delete("/{notebook_id}/history", status_code=204)
async def delete_history(
    notebook_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete all chat messages for a notebook.
    """

    notebook_repo = NotebookRepository(session)
    notebook = await notebook_repo.get_notebook(notebook_id, user_id)
    if not notebook:
        raise HTTPException(
            status_code=404, detail="Notebook not found or access denied"
        )

    chat_service = get_chat_service()
    deleted = await chat_service.delete_history(session, notebook_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="No messages found to delete")

    return None
