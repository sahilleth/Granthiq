"""
Feedback API endpoints for rating AI-generated content.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel.ext.asyncio.session import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address
from loguru import logger

from src.db.session import get_session
from src.db.repositories.feedback import FeedbackRepository
from src.db.models import FeedbackContentType, FeedbackRating
from src.services.auth import get_current_user
from src.schemas.feedback import (
    FeedbackCreateRequest,
    FeedbackResponse,
    FeedbackStatusResponse,
)

router = APIRouter(prefix="/feedback", tags=["feedback"])
limiter = Limiter(key_func=get_remote_address)


@router.post("", response_model=FeedbackResponse)
@limiter.limit("30/minute")
async def submit_feedback(
    request: Request,
    body: FeedbackCreateRequest,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Submit feedback (thumbs up/down) for AI-generated content.

    If feedback already exists for this content, it will be updated.
    This allows users to change their rating.

    Rate limited to 30 requests per minute to prevent spam.
    """
    try:
        repo = FeedbackRepository(session)

        # Map schema enum to model enum
        content_type = FeedbackContentType(body.content_type.value)
        rating = FeedbackRating(body.rating.value)

        feedback = await repo.upsert(
            user_id=user_id,
            content_type=content_type,
            content_id=body.content_id,
            rating=rating,
            comment=body.comment,
        )

        logger.info(
            f"Feedback submitted: user={user_id}, type={body.content_type}, "
            f"content={body.content_id}, rating={body.rating}"
        )

        return FeedbackResponse.model_validate(feedback)

    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit feedback")


@router.get("/{content_type}/{content_id}", response_model=FeedbackStatusResponse)
@limiter.limit("60/minute")
async def get_feedback(
    request: Request,
    content_type: str,
    content_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Get existing feedback for specific content.

    Returns whether feedback exists and the feedback details if present.
    Used to show the selected state of feedback buttons.
    """
    try:
        # Validate content_type
        try:
            content_type_enum = FeedbackContentType(content_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid content_type. Must be one of: {[e.value for e in FeedbackContentType]}",
            )

        repo = FeedbackRepository(session)
        feedback = await repo.get_by_content(
            user_id=user_id,
            content_type=content_type_enum,
            content_id=content_id,
        )

        if feedback:
            return FeedbackStatusResponse(
                has_feedback=True,
                feedback=FeedbackResponse.model_validate(feedback),
            )

        return FeedbackStatusResponse(has_feedback=False, feedback=None)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get feedback")


@router.delete("/{content_type}/{content_id}", status_code=204)
@limiter.limit("30/minute")
async def delete_feedback(
    request: Request,
    content_type: str,
    content_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete feedback for specific content.

    Allows users to remove their feedback entirely.
    """
    try:
        # Validate content_type
        try:
            content_type_enum = FeedbackContentType(content_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid content_type. Must be one of: {[e.value for e in FeedbackContentType]}",
            )

        repo = FeedbackRepository(session)
        deleted = await repo.delete_feedback(
            user_id=user_id,
            content_type=content_type_enum,
            content_id=content_id,
        )

        if not deleted:
            raise HTTPException(status_code=404, detail="Feedback not found")

        logger.info(
            f"Feedback deleted: user={user_id}, type={content_type}, content={content_id}"
        )

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete feedback")
