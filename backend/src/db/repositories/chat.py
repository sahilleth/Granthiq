from typing import List, Optional, Set
from uuid import UUID
from sqlmodel import select, desc
from sqlalchemy.orm import selectinload
from src.db.models import ChatMessage, MessageCitation
from src.db.repositories.base import BaseRepository


class ChatRepository(BaseRepository[ChatMessage]):
    """
    Repository for ChatMessage operations.
    """

    # Allowed filter fields for security (prevents SQL injection)
    ALLOWED_FILTER_FIELDS: Set[str] = {
        "notebook_id",
        "role",
    }

    def __init__(self, session):
        super().__init__(session, ChatMessage)

    async def get_notebook_history(
        self, notebook_id: UUID, limit: int = 50, offset: int = 0
    ) -> List[ChatMessage]:
        """
        Get chat history for a specific notebook with pagination.
        Eagerly loads citations and their document info for proper display.
        """
        statement = (
            select(ChatMessage)
            .where(ChatMessage.notebook_id == notebook_id)
            .options(
                selectinload(ChatMessage.citations).selectinload(
                    MessageCitation.document
                )
            )
            .order_by(desc(ChatMessage.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.exec(statement)

        return result.all()

    async def count_notebook_history(self, notebook_id: UUID) -> int:
        """Count total messages in a notebook's chat history."""
        statement = select(ChatMessage).where(ChatMessage.notebook_id == notebook_id)
        result = await self.session.exec(statement)
        return len(result.all())

    async def add_message(
        self,
        notebook_id: UUID,
        role: str,
        content: str,
        citations: Optional[List[dict]] = None,
        confidence: Optional[dict] = None,
    ) -> ChatMessage:
        """
        Add a message to the history with optional citations.

        Uses single atomic transaction for data integrity - if citation
        insert fails, the message is also rolled back.

        Args:
            notebook_id: UUID of the notebook
            role: Message role ('user' or 'assistant')
            content: Message content
            citations: Optional list of citation dicts with keys:
                       document_id, text_preview, score, page_number
            confidence: Optional confidence metadata dict (level/label/scores)

        Returns:
            The created ChatMessage with citations loaded
        """
        try:
            # Create message
            msg = ChatMessage(
                notebook_id=notebook_id,
                role=role,
                content=content,
                confidence=confidence,
            )
            self.session.add(msg)

            # Flush to get msg.id without committing transaction
            await self.session.flush()

            # Add citations if provided
            if citations:
                for cit in citations:
                    citation_obj = MessageCitation(
                        message_id=msg.id,
                        document_id=cit["document_id"],
                        text_preview=cit.get("text_preview", "")[:255],
                        score=cit.get("score", 0.0),
                        page_number=cit.get("page_number"),
                    )
                    self.session.add(citation_obj)

            # Single atomic commit for message + all citations
            await self.session.commit()
            await self.session.refresh(msg)

            return msg

        except Exception as e:
            await self.session.rollback()
            raise
