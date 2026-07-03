class NotebookLLMError(Exception):
    """Base exception for all Granthiq errors."""

    pass


class DocumentProcessingError(NotebookLLMError):
    """Raised when document processing fails."""

    pass


class YoutubeProcessingError(NotebookLLMError):
    """Raised when YouTube processing fails."""

    pass


class EmbeddingError(NotebookLLMError):
    """Raised when embedding generation fails."""

    pass


class VectorStoreError(NotebookLLMError):
    """Raised when vector store operations fail."""

    pass


class LLMError(NotebookLLMError):
    """Raised when LLM operations fail."""

    pass


class ValidationError(NotebookLLMError):
    """Raised when validation fails."""

    pass


class FileValidationError(ValidationError):
    """Raised when file validation fails."""

    pass


class FileSizeError(FileValidationError):
    """Raised when file size exceeds limit."""

    pass


class FileTypeError(FileValidationError):
    """Raised when file type is not supported."""

    pass


class RAGError(NotebookLLMError):
    """Raised when RAG pipeline fails."""

    pass


class RetrievalError(RAGError):
    """Raised when retrieval fails."""

    pass


class IngestionError(NotebookLLMError):
    """Raised when document ingestion fails."""

    pass


class ChunkingError(IngestionError):
    """Raised when document chunking fails."""

    pass


class AudioProcessingError(NotebookLLMError):
    """Raised when audio processing fails."""

    pass


class TranscriptionError(AudioProcessingError):
    """Raised when transcription fails."""

    pass


class TTSError(AudioProcessingError):
    """Raised when text-to-speech fails."""

    pass


class PodcastGenerationError(NotebookLLMError):
    """Raised when podcast generation fails."""

    pass


class DatabaseError(NotebookLLMError):
    """Raised when database operations fail."""

    pass


class CacheError(NotebookLLMError):
    """Raised when cache operations fail."""

    pass


class ConfigurationError(NotebookLLMError):
    """Raised when configuration is invalid or missing."""

    pass


class RateLimitError(NotebookLLMError):
    """Raised when rate limit is exceeded."""

    pass


class AuthenticationError(NotebookLLMError):
    """Raised when authentication fails."""

    pass


class AuthorizationError(NotebookLLMError):
    """Raised when authorization fails."""

    pass
