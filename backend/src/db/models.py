from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from enum import Enum
from sqlmodel import Field, SQLModel, Relationship, JSON
from sqlalchemy import Column, DateTime, Enum as SaEnum
# from sqlalchemy.dialects.postgresql import JSONB 
# Using generic JSON for SQLite compatibility in dev, maps to JSONB in Postgres

# Helper function for timezone-aware UTC datetime
def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ContentType(str, Enum):
    PODCAST = "podcast"
    QUIZ = "quiz"
    FLASHCARD = "flashcard"
    MINDMAP = "mindmap"
    NOTE = "note"


class FeedbackContentType(str, Enum):
    """Type of content being rated."""
    CHAT_RESPONSE = "chat_response"
    PODCAST = "podcast"
    QUIZ = "quiz"
    FLASHCARD = "flashcard"
    MINDMAP = "mindmap"
    NOTE = "note"


class FeedbackRating(str, Enum):
    """User rating for content."""
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"

class ChatRole(str, Enum):
    """Role of chat message sender for type-safe validation."""
    USER = "user"
    ASSISTANT = "assistant"

# --- Models ---

class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str = Field(default="")  # Empty for OAuth users
    is_active: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    # Relationships
    notebooks: List["Notebook"] = Relationship(back_populates="user", sa_relationship_kwargs={"cascade": "all, delete"})

class Notebook(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    title: str = Field(default="Untitled Notebook")
    
    settings: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON)) 
    
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    user: User = Relationship(back_populates="notebooks")
    documents: List["Document"] = Relationship(back_populates="notebook", sa_relationship_kwargs={"cascade": "all, delete"})
    chat_messages: List["ChatMessage"] = Relationship(back_populates="notebook", sa_relationship_kwargs={"cascade": "all, delete"})
    generated_contents: List["GeneratedContent"] = Relationship(back_populates="notebook", sa_relationship_kwargs={"cascade": "all, delete"})

class Document(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    notebook_id: UUID = Field(foreign_key="notebook.id", index=True)
    
    filename: str
    file_path: str = Field(description="S3/Local path")
    file_hash: Optional[str] = Field(default=None, index=True, description="SHA256 for deduplication")
    mime_type: str = Field(default="application/pdf")
    
    # Processing state for UI spinners
    status: ProcessingStatus = Field(default=ProcessingStatus.PENDING, index=True)
    error_message: Optional[str] = None
    chunk_count: int = Field(default=0)
    
    # Preview text for sources panel (first chunk content)
    preview: Optional[str] = Field(default=None, max_length=500)
    
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utc_now)
    )

    notebook: Notebook = Relationship(back_populates="documents")
    citations: List["MessageCitation"] = Relationship(back_populates="document", sa_relationship_kwargs={"cascade": "all, delete"})
    generated_contents: List["GeneratedContent"] = Relationship(back_populates="document")

class ChatMessage(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    notebook_id: UUID = Field(foreign_key="notebook.id", index=True)

    # Use explicit SQLAlchemy Enum to map lowercase DB values to Uppercase Python keys
    role: ChatRole = Field(sa_column=Column(SaEnum(ChatRole, native_enum=True, values_callable=lambda x: [e.value for e in x]), nullable=False))
    content: str

    # Confidence metadata (level/label/scores) for assistant messages. Persisted so
    # the confidence badge survives a page reload / history fetch. Null for user messages.
    confidence: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True))

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    notebook: Notebook = Relationship(back_populates="chat_messages")
    citations: List["MessageCitation"] = Relationship(back_populates="message", sa_relationship_kwargs={"cascade": "all, delete"})

class MessageCitation(SQLModel, table=True):
    """
    Links a chat response to the exact chunks used.
    Used for the '[1]' clickable links in the UI.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    message_id: UUID = Field(foreign_key="chatmessage.id", index=True)
    document_id: UUID = Field(foreign_key="document.id", index=True)
    
    text_preview: str = Field(description="Snippet of the cited text")
    score: float = Field(description="Relevance score from Reranker")
    page_number: Optional[int] = None
    
    message: ChatMessage = Relationship(back_populates="citations")
    document: Document = Relationship(back_populates="citations")

class GeneratedContent(SQLModel, table=True):
    """
    Stores Podcasts, Quizzes, etc.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    notebook_id: UUID = Field(foreign_key="notebook.id", index=True)
    document_id: Optional[UUID] = Field(default=None, foreign_key="document.id")
    
    content_type: ContentType = Field(index=True)
    status: ProcessingStatus = Field(default=ProcessingStatus.PENDING)
    
    # Holds the JSON structure (e.g., PodcastScript, Quiz Schema)
    content: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    # Stores the S3 URL for the generated audio file
    audio_url: Optional[str] = Field(default=None)
    
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utc_now)
    )

    notebook: Notebook = Relationship(back_populates="generated_contents")
    document: Optional[Document] = Relationship(back_populates="generated_contents")

class TaskProgress(SQLModel, table=True):
    __tablename__ = "task_progress"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    job_id: int = Field(index=True) # Linked to procrastinate_jobs.id

    # Context Links (Foreign Keys for cascading deletes)
    user_id: Optional[UUID] = Field(default=None, foreign_key="user.id", index=True)
    notebook_id: Optional[UUID] = Field(default=None, foreign_key="notebook.id", index=True)
    document_id: Optional[UUID] = Field(default=None, foreign_key="document.id", index=True)
    content_id: Optional[UUID] = Field(default=None, foreign_key="generatedcontent.id", index=True)

    progress_percent: int = Field(default=0, ge=0, le=100)
    message: Optional[str] = None
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utc_now)
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utc_now)
    )


class GoogleOAuthToken(SQLModel, table=True):
    """
    Stores Google OAuth2 tokens for users.
    Used for Google Drive integration.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True, unique=True)
    
    # OAuth tokens
    access_token: str
    refresh_token: Optional[str] = None
    token_uri: str
    client_id: str
    client_secret: str
    scopes: Optional[str] = Field(default=None, description="Comma-separated scopes")
    
    # Token expiration
    token_expiry: Optional[datetime] = Field(default=None, description="When access token expires")
    
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utc_now)
    )


class Feedback(SQLModel, table=True):
    """
    Stores user feedback (thumbs up/down) for AI-generated content.
    Supports chat responses, podcasts, quizzes, flashcards, and mindmaps.
    """
    __tablename__ = "feedback"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)

    # Content identification
    content_type: FeedbackContentType = Field(
        sa_column=Column(
            SaEnum(FeedbackContentType, native_enum=True, values_callable=lambda x: [e.value for e in x]),
            nullable=False
        )
    )
    # For chat_response: ChatMessage.id, for generated content: GeneratedContent.id
    content_id: UUID = Field(index=True)

    # Feedback data
    rating: FeedbackRating = Field(
        sa_column=Column(
            SaEnum(FeedbackRating, native_enum=True, values_callable=lambda x: [e.value for e in x]),
            nullable=False
        )
    )
    comment: Optional[str] = Field(default=None, max_length=2000)

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utc_now)
    )
