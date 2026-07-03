"""
Pydantic schemas for feedback API endpoints.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field
from enum import Enum


class FeedbackContentType(str, Enum):
    """Type of content being rated."""
    CHAT_RESPONSE = "chat_response"
    PODCAST = "podcast"
    QUIZ = "quiz"
    FLASHCARD = "flashcard"
    MINDMAP = "mindmap"


class FeedbackRating(str, Enum):
    """User rating for content."""
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class FeedbackCreateRequest(BaseModel):
    """Request body for creating/updating feedback."""
    content_type: FeedbackContentType = Field(
        ..., description="Type of content being rated"
    )
    content_id: UUID = Field(
        ..., description="ID of the content (ChatMessage.id or GeneratedContent.id)"
    )
    rating: FeedbackRating = Field(..., description="Thumbs up or thumbs down")
    comment: Optional[str] = Field(
        None, max_length=2000, description="Optional feedback comment"
    )


class FeedbackResponse(BaseModel):
    """Response body for feedback operations."""
    id: UUID
    user_id: UUID
    content_type: FeedbackContentType
    content_id: UUID
    rating: FeedbackRating
    comment: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeedbackStatusResponse(BaseModel):
    """Response for checking if feedback exists for content."""
    has_feedback: bool
    feedback: Optional[FeedbackResponse] = None
