"""
Repository for feedback operations.
"""
from typing import Optional, Set
from uuid import UUID
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.db.models import Feedback, FeedbackContentType, FeedbackRating
from src.db.repositories.base import BaseRepository


class FeedbackRepository(BaseRepository[Feedback]):
    """
    Repository for feedback CRUD operations.
    Handles user feedback for chat responses and generated content.
    """

    # Allowed filter fields for security (prevents SQL injection)
    ALLOWED_FILTER_FIELDS: Set[str] = {
        "user_id",
        "content_type",
        "content_id",
        "rating",
    }

    def __init__(self, session: AsyncSession):
        super().__init__(session, Feedback)

    async def get_by_content(
        self, user_id: UUID, content_type: FeedbackContentType, content_id: UUID
    ) -> Optional[Feedback]:
        """
        Get existing feedback for a specific content item by user.

        Args:
            user_id: The user who submitted the feedback
            content_type: Type of content (chat_response, podcast, etc.)
            content_id: ID of the content being rated

        Returns:
            Feedback record if exists, None otherwise
        """
        statement = select(Feedback).where(
            Feedback.user_id == user_id,
            Feedback.content_type == content_type,
            Feedback.content_id == content_id,
        )
        result = await self.session.exec(statement)
        return result.first()

    async def upsert(
        self,
        user_id: UUID,
        content_type: FeedbackContentType,
        content_id: UUID,
        rating: FeedbackRating,
        comment: Optional[str] = None,
    ) -> Feedback:
        """
        Create or update feedback for content.

        If feedback already exists for the user/content combination,
        updates the existing record. Otherwise creates a new one.

        Args:
            user_id: The user submitting feedback
            content_type: Type of content being rated
            content_id: ID of the content
            rating: Thumbs up or down
            comment: Optional feedback comment

        Returns:
            Created or updated Feedback record
        """
        existing = await self.get_by_content(user_id, content_type, content_id)

        if existing:
            # Update existing feedback
            existing.rating = rating
            existing.comment = comment
            self.session.add(existing)
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        # Create new feedback
        feedback = Feedback(
            user_id=user_id,
            content_type=content_type,
            content_id=content_id,
            rating=rating,
            comment=comment,
        )
        self.session.add(feedback)
        await self.session.commit()
        await self.session.refresh(feedback)
        return feedback

    async def delete_feedback(
        self, user_id: UUID, content_type: FeedbackContentType, content_id: UUID
    ) -> bool:
        """
        Delete feedback for a specific content item.

        Args:
            user_id: The user who owns the feedback
            content_type: Type of content
            content_id: ID of the content

        Returns:
            True if deleted, False if not found
        """
        existing = await self.get_by_content(user_id, content_type, content_id)
        if not existing:
            return False

        await self.session.delete(existing)
        await self.session.commit()
        return True
