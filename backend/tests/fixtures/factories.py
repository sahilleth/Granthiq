"""
Factory classes for creating test data.
Provides consistent and reusable test object creation.
"""

from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from src.db.models import User, Notebook, Document, ChatMessage, GeneratedContent, ProcessingStatus, ContentType


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class UserFactory:
    """Factory for creating test users."""

    @staticmethod
    def create(
        id: Optional[str] = None,
        email: Optional[str] = None,
        hashed_password: str = "MANAGED_BY_SUPABASE",
        is_active: bool = True,
        **kwargs
    ) -> User:
        """
        Create a User instance with sensible defaults.

        Args:
            id: User UUID (auto-generated if not provided)
            email: User email (auto-generated if not provided)
            hashed_password: Password hash
            is_active: Whether user is active
            **kwargs: Additional fields

        Returns:
            User instance (not persisted)
        """
        return User(
            id=id or uuid4(),
            email=email or f"test_{uuid4()}@notebookllm.test",
            hashed_password=hashed_password,
            is_active=is_active,
            created_at=utc_now(),
            **kwargs
        )

    @staticmethod
    async def create_persisted(session, **kwargs) -> User:
        """Create and persist a User to the database."""
        user = UserFactory.create(**kwargs)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


class NotebookFactory:
    """Factory for creating test notebooks."""

    @staticmethod
    def create(
        user_id: Optional[str] = None,
        title: str = "Test Notebook",
        settings: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Notebook:
        """
        Create a Notebook instance with sensible defaults.

        Args:
            user_id: Owner's UUID (auto-generated if not provided)
            title: Notebook title
            settings: RAG settings dictionary
            **kwargs: Additional fields

        Returns:
            Notebook instance (not persisted)
        """
        return Notebook(
            id=kwargs.pop('id', uuid4()),
            user_id=user_id or uuid4(),
            title=title,
            settings=settings or {},
            created_at=utc_now(),
            updated_at=utc_now(),
            **kwargs
        )

    @staticmethod
    async def create_persisted(session, user_id, **kwargs) -> Notebook:
        """Create and persist a Notebook to the database."""
        notebook = NotebookFactory.create(user_id=user_id, **kwargs)
        session.add(notebook)
        await session.commit()
        await session.refresh(notebook)
        return notebook


class DocumentFactory:
    """Factory for creating test documents."""

    @staticmethod
    def create(
        notebook_id: Optional[str] = None,
        filename: str = "test_document.pdf",
        file_path: Optional[str] = None,
        mime_type: str = "application/pdf",
        status: ProcessingStatus = ProcessingStatus.COMPLETED,
        chunk_count: int = 5,
        **kwargs
    ) -> Document:
        """
        Create a Document instance with sensible defaults.

        Args:
            notebook_id: Parent notebook UUID
            filename: Document filename
            file_path: Storage path
            mime_type: MIME type
            status: Processing status
            chunk_count: Number of chunks
            **kwargs: Additional fields

        Returns:
            Document instance (not persisted)
        """
        doc_id = kwargs.pop('id', uuid4())
        nb_id = notebook_id or uuid4()
        return Document(
            id=doc_id,
            notebook_id=nb_id,
            filename=filename,
            file_path=file_path or f"notebooks/test/{nb_id}/{filename}",
            mime_type=mime_type,
            status=status,
            chunk_count=chunk_count,
            created_at=utc_now(),
            **kwargs
        )

    @staticmethod
    async def create_persisted(session, notebook_id, **kwargs) -> Document:
        """Create and persist a Document to the database."""
        doc = DocumentFactory.create(notebook_id=notebook_id, **kwargs)
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc


class ChatMessageFactory:
    """Factory for creating test chat messages."""

    @staticmethod
    def create(
        notebook_id: Optional[str] = None,
        role: str = "user",
        content: str = "Test message",
        **kwargs
    ) -> ChatMessage:
        """
        Create a ChatMessage instance with sensible defaults.

        Args:
            notebook_id: Parent notebook UUID
            role: Message role (user/assistant)
            content: Message content
            **kwargs: Additional fields

        Returns:
            ChatMessage instance (not persisted)
        """
        return ChatMessage(
            id=kwargs.pop('id', uuid4()),
            notebook_id=notebook_id or uuid4(),
            role=role,
            content=content,
            created_at=utc_now(),
            **kwargs
        )

    @staticmethod
    async def create_persisted(session, notebook_id, **kwargs) -> ChatMessage:
        """Create and persist a ChatMessage to the database."""
        msg = ChatMessageFactory.create(notebook_id=notebook_id, **kwargs)
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg


class GeneratedContentFactory:
    """Factory for creating test generated content."""

    @staticmethod
    def create(
        notebook_id: Optional[str] = None,
        content_type: ContentType = ContentType.QUIZ,
        status: ProcessingStatus = ProcessingStatus.COMPLETED,
        content: Optional[Dict[str, Any]] = None,
        document_id: Optional[str] = None,
        **kwargs
    ) -> GeneratedContent:
        """
        Create a GeneratedContent instance with sensible defaults.

        Args:
            notebook_id: Parent notebook UUID
            content_type: Type of content (quiz, podcast, etc.)
            status: Processing status
            content: Generated content data
            document_id: Source document UUID
            **kwargs: Additional fields

        Returns:
            GeneratedContent instance (not persisted)
        """
        return GeneratedContent(
            id=kwargs.pop('id', uuid4()),
            notebook_id=notebook_id or uuid4(),
            document_id=document_id,
            content_type=content_type,
            status=status,
            content=content or {},
            created_at=utc_now(),
            **kwargs
        )

    @staticmethod
    async def create_persisted(session, notebook_id, **kwargs) -> GeneratedContent:
        """Create and persist GeneratedContent to the database."""
        gen_content = GeneratedContentFactory.create(notebook_id=notebook_id, **kwargs)
        session.add(gen_content)
        await session.commit()
        await session.refresh(gen_content)
        return gen_content


# Convenience functions for quick test data creation
def create_test_user(**kwargs) -> User:
    """Shorthand for UserFactory.create()."""
    return UserFactory.create(**kwargs)


def create_test_notebook(user_id, **kwargs) -> Notebook:
    """Shorthand for NotebookFactory.create()."""
    return NotebookFactory.create(user_id=user_id, **kwargs)


def create_test_document(notebook_id, **kwargs) -> Document:
    """Shorthand for DocumentFactory.create()."""
    return DocumentFactory.create(notebook_id=notebook_id, **kwargs)


def create_test_chat_message(notebook_id, **kwargs) -> ChatMessage:
    """Shorthand for ChatMessageFactory.create()."""
    return ChatMessageFactory.create(notebook_id=notebook_id, **kwargs)
