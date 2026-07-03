import hashlib
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field



class DocumentType(str, Enum):
    """Enum for the different types of sources."""
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MARKDOWN = "markdown"
    WEB = "web"
    AUDIO = "audio"
    VIDEO = "video"
    CSV = "csv"
    XLSX = "xlsx"
    PPTX = "pptx"
    IMAGE = "image"
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    """Enum for the document's lifecycle status."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"



class DocumentChunk(BaseModel):
    """
    Pydantic model for a single, processed chunk of a document.
    This model corresponds to the `document_chunks` SQL table.
    """
    chunk_id: str = Field(
        ...,
        description="Unique identifier for the chunk, generated from source and content.")
    document_id: uuid.UUID = Field(..., description="The ID of the parent document.")
    content: str = Field(..., description="The actual text content of the chunk.")
    chunk_index: int = Field(..., description="The 0-based index of the chunk within the document.")

  
    page_number: Optional[int] = Field(None, description="Page number for PDF documents.")
    start_time: Optional[float] = Field(None, description="Start time in seconds for audio/video.")
    end_time: Optional[float] = Field(None, description="End time in seconds for audio/video.")


    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True  


class UnifiedDocument(BaseModel):
    """
    The primary Pydantic model representing a single, unified document.
    This is the central object for your application's business logic and
    corresponds to the `documents` SQL table.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Primary key for the document.")
    user_id: uuid.UUID = Field(..., description="ID of the user who owns the document.")

   
    filename: str = Field(..., description="Original filename of the source document.")
    source_type: DocumentType = Field(..., description="The type of the source document.")
    status: ProcessingStatus = Field(default=ProcessingStatus.PENDING, description="Current processing status.")
    storage_path: str = Field(..., description="Path to the original file in storage (e.g., S3 URI).")

 
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    chunks: List[DocumentChunk] = Field(default_factory=list, description="A list of all chunks processed from this document.")

  
    metadata: Dict[str, Any] = Field(default_factory=dict, description="e.g., web URL, author, etc.")

  
    @property
    def chunk_count(self) -> int:
        """Returns the total number of chunks in the document."""
        return len(self.chunks)

    def add_chunk(self, content: str, chunk_index: int, **kwargs) -> DocumentChunk:
        """
        A factory method to create and add a new chunk to this document.
        This ensures consistency in chunk creation.
        """
        chunk_id = self._generate_chunk_id(content, chunk_index)
        chunk = DocumentChunk(
            chunk_id=chunk_id,
            document_id=self.id,
            content=content,
            chunk_index=chunk_index,
            **kwargs
        )
        self.chunks.append(chunk)
        return chunk

    def _generate_chunk_id(self, content: str, chunk_index: int) -> str:
        """Generates a consistent, unique ID for a chunk."""
        doc_hash = str(self.id)[:8]
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"{self.source_type.value}-{doc_hash}-{chunk_index}-{content_hash}"

    class Config:
        from_attributes = True


__all__ = [
    "DocumentType",
    "ProcessingStatus",
    "DocumentChunk",
    "UnifiedDocument",
]

