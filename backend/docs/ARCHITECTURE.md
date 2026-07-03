# System Architecture

Comprehensive architecture documentation for the Granthiq backend.

## Overview

The Granthiq backend follows a **Service-Oriented Architecture** layered on top of **FastAPI**. It emphasizes separation of concerns between API Routes, Business Logic (Services), and Data Access (Repositories).

## Architecture Diagram

![Granthiq Backend Architecture](architecture.png)

## Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Client Layer                          │
│              (Frontend / Mobile / API Clients)              │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP + JWT
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              API Router Layer                        │  │
│  │  /auth, /notebooks, /documents, /chat, /generation  │  │
│  └───────────────────────┬──────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────▼──────────────────────────────┐  │
│  │           Business Logic Layer (Services)            │  │
│  │  • ChatService          • GenerationService         │  │
│  │  • StorageService       • QueryEngineService        │  │
│  │  • DocumentProcessor    • AudioGenerator            │  │
│  │  • Suggestions Framework• Note Management           │  │
│  └───────────────────────┬──────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────▼──────────────────────────────┐  │
│  │          Data Access Layer (Repositories)            │  │
│  │  • NotebookRepository   • ChatRepository            │  │
│  │  • DocumentRepository   • ContentRepository         │  │
│  └───────────────────────┬──────────────────────────────┘  │
└──────────────────────────┼──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌─────────────┐  ┌──────────────┐
│  PostgreSQL   │  │   Qdrant    │  │   Supabase   │
│   (Data)      │  │  (Vectors)  │  │   Storage    │
└───────────────┘  └─────────────┘  └──────────────┘
```

## Core Components

### 1. Frontend Layer (Next.js)

**Stack**: Next.js 14 (App Router), Tailwind CSS, shadcn/ui.

**Key Features**:
- **Authentication**: Supabase Auth with SSR support
- **Theming**: Dark/Light mode with system preference detection (`next-themes`)
- **State Management**: React Query for server state, local state for UI
- **Real-time**: SSE for chat streaming

### 2. Database Layer (PostgreSQL)

We use **Supabase** as the primary relational database.

**Technology Stack:**
- **Driver**: `asyncpg` (High-performance async driver)
- **ORM**: `SQLModel` (Pydantic + SQLAlchemy hybrid)
- **Pattern**: **Repository Pattern** - We do not query the DB directly in routes

#### Schema Overview

**User**
- Primary key: `id` (UUID, matches Supabase Auth user ID)
- Fields: `email`, `hashed_password`, `is_active`, `created_at`
- Relationships: One-to-many with Notebooks

**Notebook**
- Primary key: `id` (UUID)
- Foreign key: `user_id` → User
- Fields: `title`, `settings` (JSON), `created_at`, `updated_at`
- Relationships: 
  - Many-to-one with User
  - One-to-many with Documents, ChatMessages, GeneratedContent

**Document**
- Primary key: `id` (UUID)
- Foreign key: `notebook_id` → Notebook
- Fields: `filename`, `file_path`, `file_hash`, `mime_type`, `status`, `error_message`, `chunk_count`, `created_at`
- Status: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`
- Relationships:
  - Many-to-one with Notebook
  - One-to-many with MessageCitations, GeneratedContent

**ChatMessage**
- Primary key: `id` (UUID)
- Foreign key: `notebook_id` → Notebook
- Fields: `role`, `content`, `created_at`
- Relationships:
  - Many-to-one with Notebook
  - One-to-many with MessageCitations

**MessageCitation**
- Primary keys: `id` (UUID)
- Foreign keys: `message_id` → ChatMessage, `document_id` → Document
- Fields: `text_preview`, `score`, `page_number`
- Purpose: Links chat responses to source document chunks

**GeneratedContent**
- Primary key: `id` (UUID)
- Foreign keys: `notebook_id` → Notebook, `document_id` → Document (optional)
- Fields: `content_type`, `status`, `content` (JSON), `audio_url`, `created_at`
- Types: `PODCAST`, `QUIZ`, `FLASHCARD`, `MINDMAP`
- Relationships:
  - Many-to-one with Notebook
  - Many-to-one with Document (optional)

#### Repository Pattern

We use the Repository Pattern to abstract database queries from business logic.

**BaseRepository** (`src/db/repositories/base.py`):
- Generic implementation of `get`, `create`, `update`, `delete`, `list`
- Uses `AsyncSession` for all operations
- Provides foundation for specific repositories

**Specific Repositories**:
- **NotebookRepository**: `get_user_notebooks()`, `create_notebook()`, `update_settings()`, `delete_notebook()`
- **DocumentRepository**: `get_by_notebook()`, `update_status()`, `get_by_hash()` (deduplication)
- **ChatRepository**: `get_notebook_history()`, `add_message()` with citations
- **ContentRepository**: `get_by_notebook()`, `get_by_document()`, `delete_content()`

### 2. Storage Layer (Object Storage)

We use **Supabase Storage** (S3-compatible) for files.

**Bucket Structure:**
- **`notebook-private`**: Stores raw user uploads (PDFs, TXT). Accessible only via backend-generated **Signed URLs**.
- **`notebook-public`**: Stores generated media (Podcasts/MP3s). Accessible via public CDN URLs.

**StorageService** (`src/services/storage.py`):
- Abstracts storage operations (local vs Supabase)
- Methods: `upload()`, `upload_stream()`, `get_url()`, `delete()`
- Handles both private (signed URLs) and public (CDN URLs) access

**Key Features:**
- **Memory-Safe Uploads**: `upload_stream()` streams files without loading into RAM
- **Signed URLs**: Private documents use temporary signed URLs (1-hour expiry)
- **Local Development**: Falls back to local file system when `provider=local`

### 3. Authentication (JWT)

**Provider**: Supabase Auth

**Flow:**
1. Client logs in via Supabase SDK (Frontend)
2. Client receives `access_token` (JWT)
3. Client sends token in `Authorization: Bearer <token>` header
4. Backend (`src/services/auth.py`) verifies signature using `SUPABASE_JWT_SECRET`
5. **JIT Provisioning**: If the user doesn't exist in the Postgres `user` table, they are created on the fly

**Security Features:**
- All endpoints (except `/health`) require Bearer token
- Token validation with expiry checking
- Row-level ownership checks in repositories (users can only access their own data)
- Signed URLs for private document access

**Auth Service** (`src/services/auth.py`):
- `get_current_user()`: FastAPI dependency that validates JWT and returns `user_id`
- Handles JIT user provisioning
- Graceful error handling for expired/invalid tokens

### 4. RAG Pipeline (LlamaIndex)

The Retrieval-Augmented Generation pipeline is built on **LlamaIndex**.

#### Ingestion Flow

1. **Upload**: User POSTs file to `/documents/upload`
2. **Storage**: Backend streams file to Supabase `notebook-private` bucket
3. **DB Record**: `Document` created with status `PENDING`
4. **Background Processing**:
   - Generate signed URL to download file
   - Download file to temp location
   - Parse content (Unstructured.io for PDFs, text extraction for others)
   - Chunk text (semantic splitting with metadata preservation)
   - Generate embeddings (Sentence Transformers)
   - Index in Qdrant with metadata (`user_id`, `notebook_id`, `document_id`, `page_number`, etc.)
5. **Status Update**: `PENDING` → `PROCESSING` → `COMPLETED` (or `FAILED` on error)

#### Query Flow

1. **User Query**: User sends message via `/chat/{notebook_id}/message`
2. **Retrieval**:
   - **Hybrid Search**: Combines semantic (vector) and keyword (BM25) search
   - **Query Fusion**: Merges results from multiple query variations
   - **HyDE**: Generates hypothetical answer first for better retrieval (with timeout fallback)
3. **Reranking**: Uses Cohere/Jina reranker to improve precision
4. **Policy Layer**: Filters low-confidence results (score < 0.10) and ensures minimum context
5. **Generation**: LLM generates answer with citations
6. **Response**: Streams tokens to client or returns complete response

**Key Components:**
- **QueryEngineService**: Orchestrates query execution
- **HybridRetriever**: Combines vector and keyword search
- **Reranker**: Improves retrieval precision
- **Policy Layer**: Enforces quality thresholds
- **Response Synthesizer**: Generates final answer from retrieved context

### 5. Content Generation

**Supported Types**: Podcasts, Quizzes, Flashcards, Mindmaps

#### Podcast Generation Pipeline

1. **Script Generation**: 
   - LLM generates dialogue script (Host/Expert format) using structured outputs (Pydantic schemas)
   - Uses specialized query engine with `top_k=20` for comprehensive context
   - Response mode: `TREE_SUMMARIZE` for detailed generation
2. **Audio Generation**:
   - `AudioGenerator` processes each dialogue turn with Kokoro TTS
   - Runs TTS in separate thread (`asyncio.to_thread()`)
   - Generates WAV files for each turn
3. **Audio Processing**:
   - Concatenates audio clips with pauses using `pydub`
   - Exports as MP3 with 192kbps bitrate
4. **Storage**: Uploads final MP3 to `notebook-public` bucket
5. **Database**: Saves script JSON and audio URL to `GeneratedContent` table

**GenerationService** (`src/services/generation/service.py`):
- Orchestrates content generation
- Handles document filtering (notebook_id, document_ids)
- Manages generation status (PENDING → PROCESSING → COMPLETED)
- Integrates with Langfuse for observability

**AudioGenerator** (`src/services/generation/audio_generator.py`):
- Kokoro TTS integration
- Multi-speaker support (voice mapping)
- Audio concatenation and export
- Error handling and cleanup

### 7. Smart Suggestions

The Suggestions Framework proactively guides users by leveraging the query engine.

**Types**:
- **Document-Based**: Analyzes uploaded content to generate starter questions (`/chat/{notebook_id}/suggestions` GET).
- **Conversation-Based**: Analyzes the last chat turn to suggest logical follow-ups (`/chat/{notebook_id}/suggestions` POST).

**Implementation**:
- Uses `LLMTextCompletionProgram` for structured extraction.
- Optimized for low latency (separate lightweight prompt).
- Cached to prevent degenerate regeneration.

### 8. Note Management

Allows manual creation of rich-text content alongside generated artifacts.

**Capabilities**:
- **CRUD Operations**: Create, Read, Update, Delete notes.
- **Rich Text**: Supports markdown-compatible note taking.
- **Context Awareness**: Notes are linked to the notebook context, similar to generated audio/quizzes.
- **Unified Interface**: Notes appear in the Studio panel alongside AI-generated content.

### 6. Observability

**Langfuse Integration**:
- Traces all LLM calls, retrievals, and generations
- Tracks token usage and costs
- Provides debugging and optimization insights

**Key Instrumentation Points**:
- Chat messages (`ChatService.send_message`)
- Content generation (`GenerationService.generate_content`)
- Document indexing (`DocumentIndexer.index_document`)
- Query execution (`QueryEngineService`)

**Logging**:
- Uses `loguru` for structured logging
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Logs include request IDs, user IDs, and context

## Data Flow Examples

### Document Upload Flow

```
1. Client → POST /documents/upload (multipart/form-data)
2. Router → Validates file size, notebook ownership
3. StorageService → Streams file to notebook-private bucket
4. DocumentRepository → Creates Document record (status: PENDING)
5. Background Task → _process_document_task()
   a. Downloads file via signed URL
   b. MainProcessor.process_file()
      - Parses document
      - Chunks text
      - Generates embeddings
   c. DocumentIndexer → Indexes chunks in Qdrant
   d. DocumentRepository → Updates status to COMPLETED
6. Client → Polls GET /notebooks/{id}/documents to check status
```

### Chat Query Flow

```
1. Client → POST /chat/{notebook_id}/message
2. Router → Validates authentication, notebook ownership
3. ChatRepository → Saves user message
4. ChatService.send_message()
   a. Retrieves chat history (last 10 messages)
   b. QueryEngineService.stream_query()
      - Builds query bundle with filters (notebook_id, user_id)
      - Hybrid retrieval (semantic + keyword)
      - Reranking
      - Policy layer filtering
      - LLM generation
   c. Streams tokens to client
   d. After stream: Saves assistant message + citations
5. Client → Receives streaming response
```

### Content Generation Flow

```
1. Client → POST /generation/{notebook_id}/podcast
2. Router → Validates authentication, notebook ownership
3. GenerationService.generate_content()
   a. Fetches documents (filtered by document_ids if provided)
   b. Builds query bundle with notebook/document filters
   c. Retrieves context (top_k=20 for comprehensive content)
   d. Generates script using structured outputs
   e. AudioGenerator.generate_podcast_audio()
      - Generates audio for each dialogue turn
      - Concatenates with pauses
      - Exports as MP3
   f. Uploads MP3 to notebook-public bucket
   g. ContentRepository → Saves GeneratedContent record
4. Client → Receives content JSON + audio URL
```

## Security Considerations

### Authentication & Authorization
- **JWT Validation**: All endpoints (except `/health`) require valid JWT
- **Ownership Checks**: Repositories verify `user_id` matches resource owner
- **Row-Level Security**: Logical isolation (can be enhanced with Supabase RLS)

### Data Protection
- **Signed URLs**: Private documents use temporary signed URLs (1-hour expiry)
- **Private Buckets**: User documents stored in private bucket, never publicly accessible
- **Public Content**: Only generated content (podcasts) stored in public bucket
- **File Validation**: File size limits, MIME type validation

### API Security
- **CORS**: Configurable CORS origins (wildcard blocked in production)
- **Input Validation**: Pydantic models validate all inputs
- **Error Handling**: Errors don't leak sensitive information
- **Rate Limiting**: Implemented with SlowAPI (100 req/min per IP)

## Performance Considerations

### Database
- **Async Operations**: All database operations use async/await
- **Connection Pooling**: SQLAlchemy connection pool for efficiency
- **Indexes**: Key fields indexed (user_id, notebook_id, document_id)

### Vector Store
- **Hybrid Search**: Combines semantic and keyword for better recall
- **Reranking**: Improves precision without sacrificing recall
- **Metadata Filtering**: Efficient filtering by user/notebook/document

### Caching
- **Future Enhancement**: Consider Redis caching for frequently accessed data
- **Query Results**: Could cache common queries

### File Processing
- **Streaming**: Files streamed, not loaded into memory
- **Background Tasks**: Heavy processing happens asynchronously
- **Health Checks**: Startup health check recovers stuck documents

## Scalability

### Horizontal Scaling
- **Stateless API**: FastAPI app can scale horizontally
- **Shared Database**: PostgreSQL handles concurrent connections
- **Shared Vector Store**: Qdrant supports distributed deployment

### Vertical Scaling
- **Async Architecture**: Handles concurrent requests efficiently
- **Connection Pooling**: Database connections managed efficiently
- **Background Tasks**: Heavy processing doesn't block requests

### Task Queue (Procrastinate)
- **PostgreSQL-based**: Uses same database, no additional infrastructure
- **Priority Queues**: CRITICAL, HIGH, STANDARD queues for different task types
- **Embedded Worker**: Runs in same process as API (cost-effective for small deployments)
- **Separate Worker**: Can be deployed independently for scaling

### Future Enhancements
- **Caching Layer**: Add Redis for caching
- **CDN**: Use CDN for public content delivery
- **Load Balancing**: Add load balancer for multiple API instances

## Monitoring & Observability

### Langfuse
- Traces all LLM interactions
- Tracks costs and token usage
- Provides debugging insights

### Logging
- Structured logging with `loguru`
- Log levels and filtering
- Request/response logging (optional)

### Health Checks
- `/health` endpoint for basic health
- Startup health check for stuck documents
- Database connection checks

### Future Enhancements
- **Prometheus Metrics**: Track API metrics, latency, errors
- **Grafana Dashboards**: Visualize metrics
- **Error Tracking**: Integrate Sentry or similar
- **Uptime Monitoring**: External monitoring services

---

## Conclusion

This architecture provides a solid foundation for a production-ready RAG system. Key strengths:

- **Separation of Concerns**: Clear boundaries between layers
- **Scalability**: Async architecture supports horizontal scaling
- **Security**: Authentication, authorization, and data protection
- **Reliability**: Error handling, health checks, and observability
- **Flexibility**: Modular design allows easy extension

For detailed implementation guides, see:
- [API Documentation](API.md)
- [Configuration Reference](CONFIGURATION.md)
- [Deployment Guide](DEPLOYMENT.md)
- [Technical Challenges](TECHNICAL_CHALLENGES_AND_SOLUTIONS.md)
