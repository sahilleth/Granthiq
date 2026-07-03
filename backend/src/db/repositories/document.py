from typing import List, Optional, Set
from uuid import UUID
from datetime import datetime
from sqlmodel import select, desc
from src.db.models import Document, ProcessingStatus
from src.db.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    """
    Repository for Document operations.
    """

    # Allowed filter fields for security (prevents SQL injection)
    ALLOWED_FILTER_FIELDS: Set[str] = {
        "notebook_id",
        "status",
        "file_hash",
        "mime_type",
        "user_id",
    }

    def __init__(self, session):
        super().__init__(session, Document)

    async def get_by_notebook(self, notebook_id: UUID) -> List[Document]:
        """Get all documents for a specific notebook."""
        statement = (
            select(Document)
            .where(Document.notebook_id == notebook_id)
            .order_by(desc(Document.created_at))
        )
        result = await self.session.exec(statement)
        return result.all()

    async def get_by_notebook_paginated(
        self, notebook_id: UUID, limit: int = 20, offset: int = 0
    ) -> List[Document]:
        """Get documents for a notebook with cursor-based pagination."""
        statement = (
            select(Document)
            .where(Document.notebook_id == notebook_id)
            .order_by(desc(Document.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.exec(statement)
        return result.all()

    async def get_many_by_ids(self, document_ids: List[UUID]) -> List[Document]:
        """
        Get multiple documents by their IDs in a single query.

        This is optimized for batch lookups to avoid N+1 query patterns
        when enriching citations with document metadata.

        Args:
            document_ids: List of document UUIDs to fetch

        Returns:
            List of Document objects (may be fewer than input if some IDs don't exist)
        """
        if not document_ids:
            return []

        # Remove duplicates while preserving order
        unique_ids = list(dict.fromkeys(document_ids))

        statement = select(Document).where(Document.id.in_(unique_ids))
        result = await self.session.exec(statement)
        return result.all()

    async def update_status(
        self,
        document_id: UUID,
        status: ProcessingStatus,
        error_message: Optional[str] = None,
    ) -> Optional[Document]:
        """Update processing status of a document."""
        update_data = {"status": status}
        if error_message:
            update_data["error_message"] = error_message

        return await self.update(document_id, update_data)

    async def get_by_hash(
        self, file_hash: str, notebook_id: UUID
    ) -> Optional[Document]:
        """Check for duplicate documents in the same notebook."""
        statement = (
            select(Document)
            .where(Document.notebook_id == notebook_id)
            .where(Document.file_hash == file_hash)
        )
        result = await self.session.exec(statement)
        return result.first()

    async def find_stuck_processing(self, threshold_time: datetime) -> List[Document]:
        """
        Find documents stuck in PROCESSING status.

        Used by dead job recovery to identify documents that have been
        stuck in processing for longer than the threshold time.

        Args:
            threshold_time: Documents updated before this time are considered stuck

        Returns:
            List of stuck documents
        """
        statement = (
            select(Document)
            .where(Document.status == ProcessingStatus.PROCESSING)
            .where(Document.updated_at < threshold_time)
        )
        result = await self.session.exec(statement)
        return result.all()

    async def reset_stuck_to_failed(
        self,
        threshold_time: datetime,
        error_message: str = "Worker crashed during processing",
    ) -> int:
        """
        Reset stuck PROCESSING documents to FAILED status.

        Args:
            threshold_time: Documents updated before this time are reset
            error_message: Error message to set on failed documents

        Returns:
            Number of documents reset
        """
        stuck_docs = await self.find_stuck_processing(threshold_time)
        count = 0

        for doc in stuck_docs:
            await self.update_status(
                doc.id, ProcessingStatus.FAILED, error_message=error_message
            )
            count += 1

        if count > 0:
            await self.session.commit()

        return count
