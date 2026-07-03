# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

# Connection pool settings - INCREASED for production workloads
# These settings apply when using direct PostgreSQL connections (port 5432)
# When using pgbouncer (port 6543), NullPool is used instead
DATABASE_POOL_SIZE = 20
"""Default database connection pool size. Supports 20 persistent connections (doubled for scale)."""

DATABASE_MAX_OVERFLOW = 25
"""Maximum number of connections that can be created beyond pool_size (increased for burst traffic)."""

DATABASE_POOL_TIMEOUT = 30
"""Seconds to wait for a connection from the pool before timing out."""

DATABASE_POOL_RECYCLE = 300


# Query limits
DEFAULT_QUERY_LIMIT = 100
"""Default limit for database queries to prevent unbounded results."""

MAX_QUERY_LIMIT = 10000
"""Maximum allowed limit for database queries."""

CHAT_HISTORY_DEFAULT_LIMIT = 50
"""Default number of chat messages to retrieve."""

CHAT_HISTORY_MAX_LIMIT = 10000
"""Maximum number of chat messages that can be retrieved."""


# =============================================================================
# FILE UPLOAD & STORAGE
# =============================================================================

# File size limits (in MB)
DEFAULT_MAX_FILE_SIZE_MB = 50
"""Default maximum file size in MB (Supabase free tier limit)."""

S3_MAX_FILE_SIZE_MB = 100
"""Maximum file size in MB for S3-compatible storage."""

# Upload chunk size (in bytes)
UPLOAD_CHUNK_SIZE_BYTES = 8192
"""Size of chunks for streaming file uploads (8KB)."""

UPLOAD_LARGE_CHUNK_SIZE_BYTES = 65536
"""Size of chunks for large file uploads (64KB)."""

# Timeouts
FILE_UPLOAD_TIMEOUT_SECONDS = 300
"""Maximum time for file upload operation (5 minutes)."""

FILE_DOWNLOAD_TIMEOUT_SECONDS = 120
"""Maximum time for file download operation (2 minutes)."""


# =============================================================================
# RAG & VECTOR SEARCH
# =============================================================================

# Chunking
DEFAULT_CHUNK_SIZE = 1000
"""Default number of characters per chunk."""

DEFAULT_CHUNK_OVERLAP = 200
"""Default number of overlapping characters between chunks."""

MIN_CHUNK_SIZE = 100
"""Minimum allowed chunk size."""

MAX_CHUNK_SIZE = 5000
"""Maximum allowed chunk size."""

# Retrieval
DEFAULT_TOP_K = 5
"""Default number of documents to retrieve."""

MAX_TOP_K = 50
"""Maximum number of documents that can be retrieved."""

DEFAULT_HYBRID_ALPHA = 0.7
"""Default weight for semantic search in hybrid retrieval (0.0-1.0)."""

# Reranking
DEFAULT_RERANKER_TOP_N = 5
"""Default number of documents to keep after reranking."""

MIN_RERANKER_SCORE = 0.6
"""Minimum reranker score to consider a document relevant."""

# Policy thresholds
MIN_CONTEXT_CHUNKS = 1
"""Minimum number of relevant chunks required to generate an answer."""

MIN_SCORE_THRESHOLD = 0.6
"""Minimum relevance score (0.0-1.0) for a chunk to be considered valid."""

# HyDE settings
HYDE_TIMEOUT_SECONDS = 2.0
"""Maximum time to wait for HyDE generation before skipping."""

HYDE_MAX_RETRIES = 2
"""Number of retries for HyDE generation."""


# =============================================================================
# LLM SETTINGS
# =============================================================================

# Request limits
DEFAULT_LLM_TEMPERATURE = 0.7
"""Default temperature for LLM generation (0.0-1.0)."""

DEFAULT_MAX_TOKENS = 2048
"""Default maximum tokens for LLM response."""

MAX_RESPONSE_TOKENS = 4096
"""Maximum tokens allowed for LLM response."""

# Timeouts and retries
LLM_REQUEST_TIMEOUT_SECONDS = 60
"""Maximum time for LLM API request."""

LLM_MAX_RETRIES = 3
"""Number of retries for failed LLM requests."""

LLM_RETRY_DELAY_SECONDS = 1.0
"""Initial delay between LLM retries (uses exponential backoff)."""

# Streaming
STREAMING_CHUNK_SIZE_CHARS = 10000
"""Maximum characters to accumulate before flushing in streaming (10KB)."""

STREAMING_FLUSH_INTERVAL_SECONDS = 5.0
"""Maximum time to wait before flushing streaming buffer."""


# =============================================================================
# RATE LIMITING
# =============================================================================

# Global limits
GLOBAL_RATE_LIMIT_PER_MINUTE = 100
"""Global rate limit per IP address per minute."""

# Endpoint-specific limits
CHAT_RATE_LIMIT_PER_MINUTE = 20
"""Rate limit for chat endpoint per IP per minute."""

UPLOAD_RATE_LIMIT_PER_HOUR = 10
"""Rate limit for file uploads per IP per hour."""

GENERATION_RATE_LIMIT_PER_HOUR = 5
"""Rate limit for content generation per IP per hour."""

# Burst limits
CHAT_BURST_LIMIT = 5
"""Number of burst requests allowed for chat endpoint."""


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================

# Thresholds
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
"""Number of failures before opening circuit."""

CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2
"""Number of successes in HALF_OPEN state before closing circuit."""

# Timeouts (in seconds)
CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
"""Time to wait before attempting recovery (OPEN → HALF_OPEN)."""

LLM_CIRCUIT_TIMEOUT_SECONDS = 60
"""Circuit breaker timeout for LLM service."""

STORAGE_CIRCUIT_TIMEOUT_SECONDS = 30
"""Circuit breaker timeout for storage service."""

VECTOR_DB_CIRCUIT_TIMEOUT_SECONDS = 30
"""Circuit breaker timeout for vector database."""


# =============================================================================
# HEALTH CHECKS
# =============================================================================

HEALTH_CHECK_TIMEOUT_SECONDS = 5.0
"""Maximum time for individual health check."""

HEALTH_CHECK_INTERVAL_SECONDS = 30
"""Interval between background health checks."""

# Document processing health
DOCUMENT_STUCK_THRESHOLD_HOURS = 1
"""Hours after which a PENDING document is considered stuck."""


# =============================================================================
# CACHING
# =============================================================================

CACHE_TTL_SECONDS = 3600
"""Default cache TTL (1 hour)."""

EMBEDDINGS_CACHE_SIZE = 1000
"""LRU cache size for embeddings."""

QUERY_ENGINE_CACHE_SIZE = 1
"""Number of query engine instances to cache (singleton pattern)."""


# =============================================================================
# BACKGROUND TASKS
# =============================================================================

BACKGROUND_TASK_TIMEOUT_SECONDS = 600
"""Maximum time for background task execution (10 minutes)."""

DOCUMENT_PROCESSING_TIMEOUT_SECONDS = 300
"""Maximum time for document processing (5 minutes)."""

INDEXING_BATCH_SIZE = 100
"""Number of documents to index in a single batch."""


# =============================================================================
# OBSERVABILITY
# =============================================================================

# Logging
LOG_CORRELATION_ID_LENGTH = 36
"""Length of correlation ID (UUID format)."""

# Tracing
TRACE_SAMPLING_RATE = 1.0
"""Sampling rate for distributed tracing (1.0 = 100%)."""

EVALUATION_SAMPLING_RATE = 0.2
"""Sampling rate for quality evaluation (0.2 = 20%)."""


# =============================================================================
# PAGINATION
# =============================================================================

DEFAULT_PAGE_SIZE = 20
"""Default number of items per page."""

MAX_PAGE_SIZE = 100
"""Maximum number of items allowed per page."""


# =============================================================================
# VALIDATION
# =============================================================================

MIN_PASSWORD_LENGTH = 8
"""Minimum password length for user accounts."""

MAX_USERNAME_LENGTH = 50
"""Maximum username length."""

MAX_EMAIL_LENGTH = 255
"""Maximum email address length."""

MIN_MESSAGE_LENGTH = 1
"""Minimum chat message length (non-empty)."""

MAX_MESSAGE_LENGTH = 10000
"""Maximum chat message length (10KB)."""

MAX_NOTEBOOK_TITLE_LENGTH = 255
"""Maximum notebook title length."""


# =============================================================================
# ERROR MESSAGES
# =============================================================================

ERROR_INSUFFICIENT_CONTEXT = (
    "I'm sorry, but I don't have enough relevant information in the provided "
    "documents to answer that question accurately."
)
"""Standard refusal message when context is insufficient."""

ERROR_PROCESSING_FAILED = (
    "Sorry, I encountered an error processing your request. Please try again."
)
"""Generic error message for processing failures."""

ERROR_RATE_LIMIT_EXCEEDED = "Rate limit exceeded. Please try again later."
"""Message shown when rate limit is exceeded."""

ERROR_FILE_TOO_LARGE = "File size exceeds maximum allowed size of {size}MB."
"""Template for file size errors (use .format(size=X))."""


# =============================================================================
# DEVELOPMENT / TESTING
# =============================================================================

TEST_DATABASE_PREFIX = "test_"
"""Prefix for test database names."""

MOCK_LLM_DELAY_SECONDS = 0.1
"""Delay for mock LLM responses in tests."""

FIXTURE_DATA_PATH = "tests/fixtures/data"
"""Path to test fixture data."""
