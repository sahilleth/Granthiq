# API Routers

Complete reference for all API endpoints in the Granthiq backend.

## Overview

All routes are registered in [`src/routers/router.py`](backend/src/routers/router.py:1) and mounted under `/api/v1`.

## Router Structure

| Router | Prefix | Description |
|--------|--------|-------------|
| [`health`](#health-router) | `/health` | Health checks |
| [`auth`](#auth-router) | `/auth` | Authentication |
| [`notebooks`](#notebooks-router) | `/notebooks` | Notebook CRUD |
| [`documents`](#documents-router) | `/documents` | Document upload & processing |
| [`chat`](#chat-router) | `/chat` | Chat & RAG queries |
| [`notes`](#notes-router) | `/notes` | Manual notes management |
| [`sources`](#sources-router) | `/sources` | External source ingestion |
| [`settings`](#settings-router) | `/settings` | User & notebook settings |
| [`generation`](#generation-router) | `/generation` | AI content generation |
| [`tasks`](#tasks-router) | `/tasks` | Background task progress |
| [`feedback`](#feedback-router) | `/feedback` | User feedback |

---

## Health Router

**File:** [`src/routers/health.py`](backend/src/routers/health.py:1)

### Endpoints

#### GET `/health`
Basic health check.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

#### GET `/health/detailed`
Detailed health check with service status.

**Response:**
```json
{
  "status": "healthy",
  "services": {
    "database": "healthy",
    "qdrant": "healthy",
    "storage": "healthy"
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

## Auth Router

**File:** [`src/routers/auth.py`](backend/src/routers/auth.py:1)

### Endpoints

#### GET `/auth/me`
Get current authenticated user.

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z"
}
```

---

## Notebooks Router

**File:** [`src/routers/notebooks.py`](backend/src/routers/notebooks.py:1)

### Endpoints

#### GET `/notebooks`
List all notebooks for the current user.

**Response:**
```json
[
  {
    "id": "uuid",
    "user_id": "uuid",
    "title": "Research Notes",
    "settings": {},
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "source_count": 5
  }
]
```

#### POST `/notebooks`
Create a new notebook.

**Request:**
```json
{
  "title": "My Notebook",
  "settings": {
    "temperature": 0.7,
    "top_k": 10
  }
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "title": "My Notebook",
  "settings": {"temperature": 0.7, "top_k": 10},
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

#### GET `/notebooks/{notebook_id}`
Get a specific notebook.

**Response:** Notebook object

#### PATCH `/notebooks/{notebook_id}`
Update notebook title or settings.

**Request:**
```json
{
  "title": "Updated Title",
  "settings": {"temperature": 0.5}
}
```

#### DELETE `/notebooks/{notebook_id}`
Delete a notebook and all associated data.

**Response:** `204 No Content`

---

## Documents Router

**File:** [`src/routers/documents.py`](backend/src/routers/documents.py:1)

### Endpoints

#### POST `/documents/upload`
Upload a file for processing.

**Rate Limit:** 10/hour per IP

**Request:** `multipart/form-data`
- `file`: File to upload (PDF, TXT, DOCX, etc.)
- `notebook_id`: UUID of the notebook

**Response:**
```json
{
  "id": "uuid",
  "notebook_id": "uuid",
  "filename": "document.pdf",
  "status": "pending",
  "message": "Document uploaded and queued for processing"
}
```

#### GET `/notebooks/{notebook_id}/documents`
List all documents in a notebook.

**Response:**
```json
[
  {
    "id": "uuid",
    "notebook_id": "uuid",
    "filename": "document.pdf",
    "mime_type": "application/pdf",
    "status": "completed",
    "chunk_count": 42,
    "preview": "First 500 chars...",
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

#### GET `/documents/{document_id}`
Get a specific document.

#### DELETE `/documents/{document_id}`
Delete a document.

**Response:** `204 No Content`

---

## Chat Router

**File:** [`src/routers/chat.py`](backend/src/routers/chat.py:1)

### Endpoints

#### GET `/chat/{notebook_id}/history`
Get chat history for a notebook.

**Response:**
```json
[
  {
    "id": "uuid",
    "notebook_id": "uuid",
    "role": "user",
    "content": "What is this document about?",
    "created_at": "2024-01-01T00:00:00Z",
    "citations": []
  },
  {
    "id": "uuid",
    "notebook_id": "uuid",
    "role": "assistant",
    "content": "This document discusses...",
    "created_at": "2024-01-01T00:00:01Z",
    "citations": [
      {
        "id": "uuid",
        "document_id": "uuid",
        "filename": "document.pdf",
        "text_preview": "Relevant text...",
        "score": 0.95,
        "page_number": 5
      }
    ]
  }
]
```

#### POST `/chat/{notebook_id}/message`
Send a message and get a response.

**Rate Limit:** 20/minute per IP

**Request:**
```json
{
  "message": "What are the key points?",
  "stream": false
}
```

**Response (non-streaming):**
```json
{
  "id": "uuid",
  "notebook_id": "uuid",
  "role": "assistant",
  "content": "The key points are...",
  "created_at": "2024-01-01T00:00:00Z",
  "citations": [...]
}
```

**Response (streaming):** `text/event-stream`

```
data: {"token": "The"}
data: {"token": " key"}
data: {"token": " points"}
...
data: {"done": true, "message_id": "uuid"}
```

#### GET `/chat/{notebook_id}/suggestions`
Get suggested questions based on document content.

**Rate Limit:** 10/minute per IP

**Response:**
```json
{
  "questions": [
    {
      "id": "uuid",
      "text": "What is the main topic?",
      "context": "Based on: document.pdf"
    }
  ],
  "generated_at": "2024-01-01T00:00:00Z",
  "document_count": 3
}
```

#### POST `/chat/{notebook_id}/suggestions`
Generate follow-up questions based on conversation.

**Request:**
```json
{
  "last_message": "The document discusses AI technology."
}
```

---

## Notes Router

**File:** [`src/routers/notes.py`](backend/src/routers/notes.py:1)

### Endpoints

#### GET `/notebooks/{notebook_id}/notes`
List all notes for a notebook.

**Response:**
```json
[
  {
    "id": "uuid",
    "notebook_id": "uuid",
    "title": "My Note",
    "content": "Note content...",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

#### POST `/notebooks/{notebook_id}/notes`
Create a new note.

**Request:**
```json
{
  "title": "Research Notes",
  "content": "Important findings..."
}
```

#### GET `/notes/{note_id}`
Get a specific note.

#### PATCH `/notes/{note_id}`
Update a note.

#### DELETE `/notes/{note_id}`
Delete a note.

---

## Sources Router

**File:** [`src/routers/sources.py`](backend/src/routers/sources.py:1)

### Endpoints

#### POST `/sources/url`
Ingest content from a URL.

**Request:**
```json
{
  "url": "https://example.com/article",
  "notebook_id": "uuid"
}
```

#### POST `/sources/youtube`
Ingest a YouTube video (transcript).

**Request:**
```json
{
  "video_url": "https://youtube.com/watch?v=...",
  "notebook_id": "uuid"
}
```

---

## Settings Router

**File:** [`src/routers/settings.py`](backend/src/routers/settings.py:1)

### Endpoints

#### GET `/settings`
Get user settings.

#### PATCH `/settings`
Update user settings.

#### GET `/notebooks/{notebook_id}/settings`
Get notebook-specific RAG settings.

#### PATCH `/notebooks/{notebook_id}/settings`
Update notebook RAG settings.

**Request:**
```json
{
  "temperature": 0.5,
  "top_k": 15,
  "enable_reranking": true
}
```

---

## Generation Router

**File:** [`src/routers/generation.py`](backend/src/routers/generation.py:1)

### Endpoints

#### GET `/generation/{notebook_id}/content`
List generated content for a notebook.

**Query Parameters:**
- `content_type`: Filter by type (podcast, quiz, flashcard, mindmap)

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "content_type": "quiz",
      "status": "completed",
      "content": {...},
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 5
}
```

#### POST `/generation/{notebook_id}/podcast`
Generate a podcast from notebook content.

**Request:**
```json
{
  "document_ids": ["uuid1", "uuid2"],
  "voice_style": "conversational"
}
```

**Response:**
```json
{
  "id": "uuid",
  "content_type": "podcast",
  "status": "processing",
  "message": "Podcast generation started"
}
```

#### POST `/generation/{notebook_id}/quiz`
Generate a quiz.

**Request:**
```json
{
  "document_ids": ["uuid"],
  "num_questions": 10
}
```

#### POST `/generation/{notebook_id}/flashcards`
Generate flashcards.

**Request:**
```json
{
  "document_ids": ["uuid"],
  "num_cards": 20
}
```

#### POST `/generation/{notebook_id}/mindmap`
Generate a mind map.

**Request:**
```json
{
  "document_ids": ["uuid"]
}
```

#### GET `/generation/content/{content_id}`
Get specific generated content.

#### DELETE `/generation/content/{content_id}`
Delete generated content.

---

## Tasks Router

**File:** [`src/routers/tasks.py`](backend/src/routers/tasks.py:1)

### Endpoints

#### GET `/tasks/{task_id}`
Get task progress.

**Response:**
```json
{
  "id": "uuid",
  "job_id": 123,
  "progress_percent": 75,
  "message": "Processing chunks...",
  "status": "processing",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:01:00Z"
}
```

---

## Feedback Router

**File:** [`src/routers/feedback.py`](backend/src/routers/feedback.py:1)

### Endpoints

#### POST `/feedback`
Submit feedback for AI-generated content.

**Request:**
```json
{
  "content_type": "chat_response",
  "content_id": "uuid",
  "rating": "thumbs_up",
  "comment": "Very helpful response!"
}
```

#### GET `/feedback/{content_id}`
Get feedback for specific content.

---

## Error Responses

All endpoints return consistent error formats:

### 400 Bad Request
```json
{
  "detail": "Invalid request: missing required field"
}
```

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```

### 403 Forbidden
```json
{
  "detail": "Access denied to this resource"
}
```

### 404 Not Found
```json
{
  "detail": "Resource not found"
}
```

### 429 Too Many Requests
```json
{
  "detail": "Rate limit exceeded",
  "retry_after": 60
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error"
}
```

## Rate Limiting

| Endpoint | Limit | Window |
|----------|-------|--------|
| All endpoints | 100 | per minute per IP |
| Chat messages | 20 | per minute per IP |
| Document uploads | 10 | per hour per IP |
| Suggestions | 10 | per minute per IP |

Rate limit headers are included in all responses:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704067200
```
