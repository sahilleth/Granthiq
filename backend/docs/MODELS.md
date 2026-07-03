# Database Models

Complete reference for all database models in the Granthiq backend.

## Overview

The backend uses **SQLModel** (a hybrid of Pydantic and SQLAlchemy) for database models. All models use UUID primary keys and timezone-aware datetime fields.

## Enums

### ProcessingStatus
Tracks the state of async operations like document processing and content generation.

```python
class ProcessingStatus(str, Enum):
    PENDING = "pending"       # Waiting to be processed
    PROCESSING = "processing" # Currently being processed
    COMPLETED = "completed"   # Successfully finished
    FAILED = "failed"         # Error occurred
```

### ContentType
Types of AI-generated content supported.

```python
class ContentType(str, Enum):
    PODCAST = "podcast"
    QUIZ = "quiz"
    FLASHCARD = "flashcard"
    MINDMAP = "mindmap"
    NOTE = "note"
```

### ChatRole
Valid roles for chat messages.

```python
class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
```

### FeedbackContentType
Types of content that can receive feedback.

```python
class FeedbackContentType(str, Enum):
    CHAT_RESPONSE = "chat_response"
    PODCAST = "podcast"
    QUIZ = "quiz"
    FLASHCARD = "flashcard"
    MINDMAP = "mindmap"
    NOTE = "note"
```

### FeedbackRating
User feedback options.

```python
class FeedbackRating(str, Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
```

## Core Models

### User

Represents a user in the system. Users are provisioned automatically on first authentication (JIT provisioning).

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key, matches Supabase Auth user ID |
| `email` | str | Unique email address (indexed) |
| `hashed_password` | str | Empty for OAuth users |
| `is_active` | bool | Account status |
| `created_at` | datetime | When user was created (timezone-aware) |

**Relationships:**
- `notebooks`: One-to-many with [`Notebook`](backend/src/db/models.py:64)

---

### Notebook

A container for documents, chat history, and generated content.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `user_id` | UUID | Foreign key → User.id (indexed) |
| `title` | str | Notebook name (default: "Untitled Notebook") |
| `settings` | dict | JSON configuration for RAG settings |
| `created_at` | datetime | Creation timestamp |
| `updated_at` | datetime | Last modification timestamp |

**Relationships:**
- `user`: Many-to-one with [`User`](backend/src/db/models.py:51)
- `documents`: One-to-many with [`Document`](backend/src/db/models.py:85) (cascade delete)
- `chat_messages`: One-to-many with [`ChatMessage`](backend/src/db/models.py:115) (cascade delete)
- `generated_contents`: One-to-many with [`GeneratedContent`](backend/src/db/models.py:147) (cascade delete)

---

### Document

Represents an uploaded file or external source.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `notebook_id` | UUID | Foreign key → Notebook.id (indexed) |
| `filename` | str | Original file name |
| `file_path` | str | Storage path (S3/Local) |
| `file_hash` | str | SHA256 hash for deduplication (indexed) |
| `mime_type` | str | File type (default: "application/pdf") |
| `status` | ProcessingStatus | Current processing state |
| `error_message` | str | Error details if failed |
| `chunk_count` | int | Number of text chunks created |
| `preview` | str | First 500 chars of content (for UI) |
| `created_at` | datetime | Upload timestamp |
| `updated_at` | datetime | Last update timestamp |

**Relationships:**
- `notebook`: Many-to-one with [`Notebook`](backend/src/db/models.py:64)
- `citations`: One-to-many with [`MessageCitation`](backend/src/db/models.py:131) (cascade delete)
- `generated_contents`: One-to-many with [`GeneratedContent`](backend/src/db/models.py:147)

**Status Flow:**
```
PENDING → PROCESSING → COMPLETED
                    ↘ FAILED
```

---

### ChatMessage

Individual messages in a notebook's chat history.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `notebook_id` | UUID | Foreign key → Notebook.id (indexed) |
| `role` | ChatRole | USER or ASSISTANT |
| `content` | str | Message text |
| `created_at` | datetime | When message was sent |

**Relationships:**
- `notebook`: Many-to-one with [`Notebook`](backend/src/db/models.py:64)
- `citations`: One-to-many with [`MessageCitation`](backend/src/db/models.py:131) (cascade delete)

---

### MessageCitation

Links chat responses to source document chunks for citations.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `message_id` | UUID | Foreign key → ChatMessage.id (indexed) |
| `document_id` | UUID | Foreign key → Document.id |
| `text_preview` | str | Snippet of cited text |
| `score` | float | Relevance score from reranker |
| `page_number` | int | Page number (if available) |

**Relationships:**
- `message`: Many-to-one with [`ChatMessage`](backend/src/db/models.py:115)
- `document`: Many-to-one with [`Document`](backend/src/db/models.py:85)

---

### GeneratedContent

Stores AI-generated content like podcasts, quizzes, flashcards, and mindmaps.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `notebook_id` | UUID | Foreign key → Notebook.id (indexed) |
| `document_id` | UUID | Optional foreign key → Document.id |
| `content_type` | ContentType | Type of content generated |
| `status` | ProcessingStatus | Generation state |
| `content` | dict | JSON structure with content data |
| `audio_url` | str | URL to generated audio (for podcasts) |
| `created_at` | datetime | Creation timestamp |
| `updated_at` | datetime | Last update timestamp |

**Relationships:**
- `notebook`: Many-to-one with [`Notebook`](backend/src/db/models.py:64)
- `document`: Many-to-one with [`Document`](backend/src/db/models.py:85)

---

### TaskProgress

Tracks progress of background tasks (document processing, content generation).

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `job_id` | int | Linked to procrastinate_jobs.id (indexed) |
| `user_id` | UUID | Foreign key → User.id (indexed) |
| `notebook_id` | UUID | Foreign key → Notebook.id (indexed) |
| `document_id` | UUID | Foreign key → Document.id (indexed) |
| `content_id` | UUID | Foreign key → GeneratedContent.id (indexed) |
| `progress_percent` | int | 0-100 completion percentage |
| `message` | str | Status message for UI |
| `updated_at` | datetime | Last progress update |
| `created_at` | datetime | Task creation time |

---

### Feedback

User feedback (thumbs up/down) for AI-generated content.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `user_id` | UUID | Foreign key → User.id (indexed) |
| `content_type` | FeedbackContentType | What is being rated |
| `content_id` | UUID | ID of the rated content (indexed) |
| `rating` | FeedbackRating | thumbs_up or thumbs_down |
| `comment` | str | Optional feedback text (max 2000 chars) |
| `created_at` | datetime | When feedback was submitted |
| `updated_at` | datetime | Last modification |

## Database Schema Diagram

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    User     │────<│  Notebook   │>────│  Document   │
└─────────────┘     └─────────────┘     └─────────────┘
                            │                   │
                            ▼                   ▼
                    ┌─────────────┐     ┌─────────────┐
                    │ ChatMessage │<────│   Message   │
                    └─────────────┘     │  Citation   │
                            │           └─────────────┘
                            ▼
                    ┌─────────────┐
                    │  Generated  │
                    │   Content   │
                    └─────────────┘
                            │
                            ▼
                    ┌─────────────┐
                    │   Feedback  │
                    └─────────────┘
```

## Indexes

The following indexes are defined for performance:

| Table | Column | Purpose |
|-------|--------|---------|
| user | email | Unique lookup |
| notebook | user_id | List user's notebooks |
| document | notebook_id | List notebook documents |
| document | file_hash | Deduplication check |
| chatmessage | notebook_id | Fetch chat history |
| messagecitation | message_id | Load citations |
| generatedcontent | notebook_id | List generated content |
| task_progress | job_id | Lookup by job |
| task_progress | user_id | User's tasks |
| task_progress | notebook_id | Notebook tasks |
| task_progress | document_id | Document tasks |
| feedback | user_id | User's feedback |
| feedback | content_id | Content feedback |

## Cascade Deletes

The following relationships cascade deletes:

- User → Notebooks (delete user = delete all notebooks)
- Notebook → Documents (delete notebook = delete all documents)
- Notebook → ChatMessages (delete notebook = delete all messages)
- Notebook → GeneratedContent (delete notebook = delete all content)
- Document → Citations (delete document = delete all citations)
- ChatMessage → Citations (delete message = delete all citations)

## Usage Examples

### Create a Notebook

```python
from src.db.models import Notebook
from uuid import uuid4

notebook = Notebook(
    id=uuid4(),
    user_id=user_id,
    title="Research Notes",
    settings={"temperature": 0.7}
)
```

### Update Document Status

```python
from src.db.models import Document, ProcessingStatus

document.status = ProcessingStatus.COMPLETED
document.chunk_count = 42
```

### Add Citation

```python
from src.db.models import MessageCitation

citation = MessageCitation(
    message_id=message_id,
    document_id=document_id,
    text_preview="Relevant text snippet...",
    score=0.95,
    page_number=5
)
```
