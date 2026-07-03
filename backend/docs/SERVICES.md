# Services Documentation

Complete reference for all business logic services in the Granthiq backend.

## Overview

Services contain the core business logic of the application. They are organized by domain and follow the Single Responsibility Principle.

## Service Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    API Routers                          │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                   Services Layer                        │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────────┐  │
│  │   Chat      │ │ Generation  │ │    Ingestion     │  │
│  │  Service    │ │  Service    │ │   Pipeline       │  │
│  └─────────────┘ └─────────────┘ └──────────────────┘  │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────────┐  │
│  │   Query     │ │   Storage   │ │    Indexer       │  │
│  │   Engine    │ │   Service   │ │                  │  │
│  └─────────────┘ └─────────────┘ └──────────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│              Data Access Layer (Repositories)           │
└─────────────────────────────────────────────────────────┘
```

---

## Chat Service

**File:** [`src/services/chat/service.py`](backend/src/services/chat/service.py:1)

### Purpose
Handles chat conversations, message history, and RAG-powered responses.

### Key Methods

#### `send_message()`
Process a user message and generate a response.

```python
async def send_message(
    self,
    session: AsyncSession,
    notebook_id: UUID,
    user_id: UUID,
    message: str,
    stream: bool = False
) -> Union[ChatMessageResponse, AsyncIterator[str]]
```

**Parameters:**
- `session`: Database session
- `notebook_id`: Notebook context
- `user_id`: Authenticated user
- `message`: User's message text
- `stream`: Whether to stream the response

**Returns:**
- Non-streaming: [`ChatMessageResponse`](backend/src/routers/chat.py:38)
- Streaming: Async iterator of SSE events

#### `generate_suggestions()`
Generate contextual question suggestions.

```python
async def generate_suggestions(
    self,
    session: AsyncSession,
    notebook_id: UUID,
    user_id: UUID,
    conversation_context: Optional[str] = None
) -> SuggestionsResponse
```

### Features
- Streaming and non-streaming responses
- Automatic citation extraction
- Context-aware suggestions
- Chat history management

---

## Generation Service

**File:** [`src/services/generation/service.py`](backend/src/services/generation/service.py:1)

### Purpose
Orchestrates AI content generation (podcasts, quizzes, flashcards, mindmaps).

### Key Methods

#### `generate_content()`
Generate AI content from notebook documents.

```python
async def generate_content(
    self,
    session: AsyncSession,
    content_type: Literal["podcast", "quiz", "flashcard", "mindmap"],
    notebook_id: UUID,
    document_ids: Optional[List[UUID]] = None,
    user_id: Optional[UUID] = None,
    content_id: Optional[UUID] = None
) -> Union[PodcastScript, Quiz, FlashcardDeck, MindMap, None]
```

**Content Types:**
- **Podcast**: Dialogue-style audio content with script and MP3
- **Quiz**: Multiple-choice questions with answers
- **Flashcards**: Question/answer pairs for study
- **MindMap**: Hierarchical concept visualization

### Generators

Each content type has a dedicated generator:

| Generator | File | Purpose |
|-----------|------|---------|
| [`PodcastGenerator`](backend/src/services/generation/generators/podcast.py:1) | `generators/podcast.py` | Creates dialogue scripts |
| [`QuizGenerator`](backend/src/services/generation/generators/quiz.py:1) | `generators/quiz.py` | Creates quiz questions |
| [`FlashcardGenerator`](backend/src/services/generation/generators/flashcard.py:1) | `generators/flashcard.py` | Creates study cards |
| [`MindMapGenerator`](backend/src/services/generation/generators/mindmap.py:1) | `generators/mindmap.py` | Creates concept maps |

### Audio Generation

**File:** [`src/services/generation/audio_generator.py`](backend/src/services/generation/audio_generator.py:1)

Uses **Kokoro TTS** to convert podcast scripts to audio:
- Multi-speaker support (Host/Expert voices)
- WAV generation per dialogue turn
- MP3 concatenation with pauses
- Uploads to public storage bucket

---

## Query Engine Service

**File:** [`src/services/query/query_engine.py`](backend/src/services/query/query_engine.py:1)

### Purpose
RAG (Retrieval-Augmented Generation) query execution using LlamaIndex.

### Key Methods

#### `query()`
Execute a RAG query.

```python
async def query(
    self,
    query_str: str,
    filters: Optional[Dict[str, Any]] = None
) -> Union[Response, AsyncStreamingResponse]
```

#### `astream_query()`
Stream a RAG query response.

```python
async def astream_query(
    self,
    query_str: str,
    filters: Optional[Dict[str, Any]] = None
) -> AsyncIterator[str]
```

### RAG Pipeline Features

1. **Hybrid Search**: Combines semantic (vector) and keyword (BM25) search
2. **Query Fusion**: Expands queries for better retrieval
3. **HyDE**: Hypothetical Document Embeddings for improved relevance
4. **Reranking**: Cohere/Jina reranker for precision
5. **Policy Layer**: Filters low-confidence results

### Configuration

Controlled via [`RagSettings`](backend/src/config.py:1):

```python
RAG__CHUNK_SIZE=1000
RAG__TOP_K_RESULTS=30
RAG__ENABLE_RERANKING=true
RAG__USE_HYDE=true
RAG__ENABLE_QUERY_FUSION=true
```

---

## Ingestion Pipeline

**File:** [`src/services/ingestion/pipeline.py`](backend/src/services/ingestion/pipeline.py:1)

### Purpose
End-to-end document processing from upload to vector index.

### Pipeline Stages

```
Upload → Parse → Chunk → Embed → Index
```

1. **Upload**: Receive file via API
2. **Parse**: Extract text (PDF, DOCX, Audio, Web, YouTube)
3. **Chunk**: Split into semantic chunks
4. **Embed**: Generate vector embeddings
5. **Index**: Store in Qdrant vector database

### Processors

| Processor | File | Supported Types |
|-----------|------|-----------------|
| [`UnstructuredDocumentProcessor`](backend/src/services/ingestion/documents/document_processor.py:1) | `documents/document_processor.py` | PDF, DOCX, TXT, MD |
| [`AudioTranscriber`](backend/src/services/ingestion/audio/audio_processor.py:1) | `audio/audio_processor.py` | MP3, WAV, M4A |
| [`WebProcessor`](backend/src/services/ingestion/web/web_processor.py:1) | `web/web_processor.py` | URLs, HTML |
| [`YoutubeProcessor`](backend/src/services/ingestion/yt/youtube_processor.py:1) | `yt/youtube_processor.py` | YouTube videos |

### Main Processor

**File:** [`src/services/ingestion/main_processor.py`](backend/src/services/ingestion/main_processor.py:1)

Routes files to appropriate processors:

```python
async def process_file(
    self,
    file_path: Path,
    notebook_id: UUID,
    document_id: UUID
) -> UnifiedDocument
```

---

## Document Indexer

**File:** [`src/services/indexer/indexer.py`](backend/src/services/indexer/indexer.py:1)

### Purpose
Indexes processed documents into Qdrant vector store.

### Key Methods

#### `index_document()`
Index a processed document.

```python
async def index_document(
    self,
    document: UnifiedDocument,
    notebook_id: UUID,
    user_id: UUID,
    document_id: UUID
) -> int
```

**Returns:** Number of chunks indexed

### Features
- Batch embedding generation
- Metadata preservation (page numbers, etc.)
- Duplicate detection via file hash
- Incremental indexing support

---

## Storage Service

**File:** [`src/services/storage.py`](backend/src/services/storage.py:1)

### Purpose
Abstracts file storage operations (local, S3, Supabase).

### Key Methods

#### `upload_stream()`
Stream upload without loading into memory.

```python
async def upload_stream(
    self,
    file_obj: BinaryIO,
    path: str,
    bucket: str,
    mime_type: str
) -> str
```

#### `get_url()`
Get access URL (signed or public).

```python
async def get_url(
    self,
    path: str,
    bucket: str,
    private: bool = False,
    expiry: int = 3600
) -> str
```

### Buckets

| Bucket | Purpose | Access |
|--------|---------|--------|
| `notebook-private` | Document uploads | Signed URLs only |
| `notebook-public` | Generated audio/podcasts | Public CDN URLs |

---

## Auth Service

**File:** [`src/services/auth.py`](backend/src/services/auth.py:1)

### Purpose
JWT authentication and user provisioning.

### Key Functions

#### `get_current_user()`
FastAPI dependency for authentication.

```python
async def get_current_user(
    authorization: str = Header(...)
) -> UUID
```

**Features:**
- JWT validation using Supabase secret
- Automatic user provisioning (JIT)
- Token expiry checking

---

## LLM Factory

**File:** [`src/services/llm/factory.py`](backend/src/services/llm/factory.py:1)

### Purpose
Creates LLM instances for different providers.

### Supported Providers

| Provider | Models | Use Case |
|----------|--------|----------|
| Gemini | gemini-2.5-flash, gemini-pro | Default chat & generation |
| OpenAI | gpt-4, gpt-3.5-turbo | Alternative LLM |
| Groq | llama-3.1-70b, mixtral | Fast inference |

### Usage

```python
from src.services.llm.factory import create_llamaindex_llm

llm = create_llamaindex_llm(
    provider="gemini",
    api_key="...",
    model="gemini-2.5-flash",
    temperature=0.7
)
```

---

## Reranker Service

**File:** [`src/services/reranker/reranker.py`](backend/src/services/reranker/reranker.py:1)

### Purpose
Reranks retrieved chunks for better relevance.

### Supported Rerankers

| Provider | Model | Notes |
|----------|-------|-------|
| Cohere | rerank-english-v2.0 | Recommended |
| Jina | jina-reranker-v1 | Alternative |

### Configuration

```python
RAG__ENABLE_RERANKING=true
RAG__RERANKER_TOP_N=10
COHERE_API_KEY=...
```

---

## Observability (Langfuse)

**File:** [`src/services/observability/langfuse_config.py`](backend/src/services/observability/langfuse_config.py:1)

### Purpose
Tracing and observability for LLM operations.

### Traced Operations

- Chat messages ([`ChatService.send_message`](backend/src/services/chat/service.py:94))
- Content generation ([`GenerationService.generate_content`](backend/src/services/generation/service.py:85))
- Document indexing ([`DocumentIndexer.index_document`](backend/src/services/indexer/indexer.py:1))
- Query execution ([`QueryEngineService.query`](backend/src/services/query/query_engine.py:1))

### Configuration

```python
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## Service Dependencies

```
ChatService
├── QueryEngineService
├── ChatRepository
└── NotebookRepository

GenerationService
├── QueryEngineBuilder
├── PodcastGenerator
├── QuizGenerator
├── FlashcardGenerator
├── MindMapGenerator
├── AudioGenerator
└── ContentRepository

QueryEngineService
├── QueryEngineBuilder
├── Retriever
├── Reranker
└── LLM

IngestionPipeline
├── MainProcessor
├── DocumentIndexer
├── StorageService
└── DocumentRepository
```

---

## Best Practices

1. **Use Singleton Pattern**: Services like [`GenerationService`](backend/src/services/generation/service.py:47) use singletons for expensive initialization
2. **Dependency Injection**: Use FastAPI's `Depends()` for service injection
3. **Async Operations**: All I/O-bound operations are async
4. **Error Handling**: Services log errors and raise appropriate HTTP exceptions
5. **Observability**: Use `@observe` decorator for Langfuse tracing
