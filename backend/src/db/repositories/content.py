from typing import List, Optional, Union, Set
from uuid import UUID
from datetime import datetime
from sqlmodel import select, desc, delete
from src.db.models import GeneratedContent, ProcessingStatus, ContentType
from src.db.repositories.base import BaseRepository


class ContentRepository(BaseRepository[GeneratedContent]):
    """
    Repository for GeneratedContent operations.
    """

    # Allowed filter fields for security (prevents SQL injection)
    ALLOWED_FILTER_FIELDS: Set[str] = {
        "notebook_id",
        "document_id",
        "content_type",
        "status",
    }

    def __init__(self, session):
        super().__init__(session, GeneratedContent)

    async def get_by_notebook(self, notebook_id: UUID) -> List[GeneratedContent]:
        """Get all generated content for a specific notebook."""
        statement = (
            select(GeneratedContent)
            .where(GeneratedContent.notebook_id == notebook_id)
            .order_by(desc(GeneratedContent.created_at))
        )
        result = await self.session.exec(statement)
        return result.all()

    async def get_by_notebook_paginated(
        self,
        notebook_id: UUID,
        limit: int = 20,
        offset: int = 0,
        content_type: Optional[ContentType] = None,
    ) -> List[GeneratedContent]:
        """Get generated content for a notebook with cursor-based pagination."""
        statement = (
            select(GeneratedContent)
            .where(GeneratedContent.notebook_id == notebook_id)
            .order_by(desc(GeneratedContent.created_at))
            .limit(limit)
            .offset(offset)
        )
        if content_type:
            statement = statement.where(GeneratedContent.content_type == content_type)

        result = await self.session.exec(statement)
        return result.all()

    async def create_content(
        self,
        notebook_id: UUID,
        content_type: Union[str, ContentType],
        document_id: Optional[UUID] = None,
        status: ProcessingStatus = ProcessingStatus.PENDING,
        content: Optional[dict] = None,
    ) -> GeneratedContent:
        """Initialize a content generation record."""
        # Convert string to ContentType enum if needed
        if isinstance(content_type, str):
            content_type = ContentType(content_type)

        content_record = GeneratedContent(
            notebook_id=notebook_id,
            document_id=document_id,
            content_type=content_type,
            status=status,
            content=content or {},  # Use provided content or empty dict
        )
        return await self.create(content_record)

    async def update_content(
        self,
        content_id: UUID,
        content_data: dict,
        content_type: ContentType,
        document_id: Optional[UUID] = None,
        status: ProcessingStatus = ProcessingStatus.COMPLETED,
        audio_url: Optional[str] = None,
    ) -> Optional[GeneratedContent]:
        """Update content payload and status."""
        values = {
            "content": content_data,
            "status": status,
            "content_type": content_type,
            "document_id": document_id,
        }
        if audio_url:
            values["audio_url"] = audio_url

        return await self.update(content_id, values)

    async def delete_content(
        self,
        notebook_id: UUID,
        content_type: ContentType,
        document_id: Optional[UUID] = None,
    ) -> bool:
        """
        Delete content records matching the criteria.
        If document_id is None, deletes notebook-level content (document_id IS NULL).
        """
        statement = (
            delete(GeneratedContent)
            .where(GeneratedContent.notebook_id == notebook_id)
            .where(GeneratedContent.content_type == content_type)
        )

        if document_id is not None:
            statement = statement.where(GeneratedContent.document_id == document_id)
        else:
            statement = statement.where(GeneratedContent.document_id.is_(None))

        result = await self.session.exec(statement)
        await self.session.commit()

        # Check if any rows were affected
        return result.rowcount > 0 if hasattr(result, "rowcount") else True

    async def get_by_document(
        self, document_id: UUID, content_type: Optional[ContentType] = None
    ) -> List[GeneratedContent]:
        """Get all generated content for a specific document, optionally filtered by type."""
        statement = (
            select(GeneratedContent)
            .where(GeneratedContent.document_id == document_id)
            .order_by(desc(GeneratedContent.created_at))
        )
        if content_type:
            statement = statement.where(GeneratedContent.content_type == content_type)

        result = await self.session.exec(statement)
        return result.all()

    async def update_status(
        self,
        content_id: UUID,
        status: ProcessingStatus,
        error_message: Optional[str] = None,
    ) -> Optional[GeneratedContent]:
        """Update content status (for background task updates)."""
        values = {"status": status}
        if error_message:
            values["error_message"] = error_message
        return await self.update(content_id, values)

    async def find_stuck_processing(
        self, threshold_time: datetime
    ) -> List[GeneratedContent]:
        """
        Find content stuck in PROCESSING status.

        Used by dead job recovery to identify content that has been
        stuck in processing for longer than the threshold time.

        Args:
            threshold_time: Content updated before this time is considered stuck

        Returns:
            List of stuck content records
        """
        statement = (
            select(GeneratedContent)
            .where(GeneratedContent.status == ProcessingStatus.PROCESSING)
            .where(GeneratedContent.updated_at < threshold_time)
        )
        result = await self.session.exec(statement)
        return result.all()

    async def reset_stuck_to_failed(
        self,
        threshold_time: datetime,
        error_message: str = "Worker crashed during generation",
    ) -> int:
        """
        Reset stuck PROCESSING content to FAILED status.

        Args:
            threshold_time: Content updated before this time is reset
            error_message: Error message to set on failed content

        Returns:
            Number of content records reset
        """
        stuck_content = await self.find_stuck_processing(threshold_time)
        count = 0

        for content in stuck_content:
            await self.update_status(
                content.id, ProcessingStatus.FAILED, error_message=error_message
            )
            count += 1

        if count > 0:
            await self.session.commit()

        return count
