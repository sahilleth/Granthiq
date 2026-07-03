import threading
from functools import lru_cache
from typing import List, Optional, Union, Dict, Any
from pathlib import Path
from uuid import UUID
from loguru import logger

from src.schemas.document import UnifiedDocument, DocumentType
from src.services.ingestion.documents.document_processor import UnstructuredDocumentProcessor
from src.services.ingestion.audio.audio_processor import AudioTranscriber
from src.services.ingestion.web.web_processor import WebProcessor
from src.services.ingestion.yt.youtube_processor import YoutubeProcessor
from src.services.ingestion.gdrive.google_drive_processor import GoogleDriveProcessor
from src.services.ingestion.chunk_manager import apply_chunking_to_document_non_destructive
from src.config import get_settings
from src.utils.exceptions import DocumentProcessingError
from src.services.embeddings.embedding_config import get_llamaindex_embed_model, configure_llamaindex_embed_model
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
# DB Integration
from src.db.session import async_session_factory
from src.db.repositories.document import DocumentRepository
from src.db.models import ProcessingStatus


# ═══════════════════════════════════════════════════════════════════════════════
# Thread-safe global embedding model cache
# ═══════════════════════════════════════════════════════════════════════════════
_SHARED_EMBED_MODEL: Optional[HuggingFaceEmbedding] = None
_model_lock = threading.Lock()
_model_initialized = threading.Event()

def _get_cached_embed_model(settings) -> Optional[HuggingFaceEmbedding]:
    """
    Get or create the shared embedding model in a thread-safe manner.

    Uses double-checked locking pattern for efficient thread safety.
    """
    global _SHARED_EMBED_MODEL

    # Fast path: check without lock
    if _model_initialized.is_set() and _SHARED_EMBED_MODEL is not None:
        return _SHARED_EMBED_MODEL

    # Slow path: acquire lock and initialize
    with _model_lock:
        # Double-check after acquiring lock
        if _SHARED_EMBED_MODEL is not None:
            return _SHARED_EMBED_MODEL

        logger.info("Creating HuggingFace embedder for semantic chunking...")

        try:
            model_name = settings.embedding.model

            # Auto-detect device
            device = "cpu"
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    device = "mps"
            except ImportError:
                pass

            logger.info(f"Using device '{device}' for HuggingFaceEmbedding")

            # Create HuggingFace embedder directly
            embed_model = HuggingFaceEmbedding(
                model_name=model_name,
                device=device,
            )
            logger.info(
                f"Successfully created HuggingFaceEmbedding: {model_name} "
                f"(type: {type(embed_model).__name__})"
            )

            # Cache the successful model
            _SHARED_EMBED_MODEL = embed_model
            _model_initialized.set()

            return embed_model

        except Exception as create_error:
            logger.warning(
                f"Failed to create HuggingFace embedder: {type(create_error).__name__}: "
                f"{str(create_error)[:200]}"
            )
            return None

class MainProcessor:
    """
    Core Ingestion Service.
    Responsible for routing files/URLs to specific processors (PDF, Audio, Web, etc.)
    and applying chunking strategies.
    
    Does NOT handle indexing (use IngestionPipeline for that).
    """
    
    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        """
        Initialize the main processor.
        
        Args:
            chunk_size: Override default chunk size
            chunk_overlap: Override default chunk overlap
        """
        self.settings = get_settings()
        self.document_processor = UnstructuredDocumentProcessor()
        self.audio_processor = AudioTranscriber(
            api_key=self.settings.assemblyai.api_key or ""
        )
        self.web_processor = WebProcessor()
        self.youtube_processor = YoutubeProcessor()
        self.gdrive_processor = GoogleDriveProcessor()
        
  
        self.chunk_size = chunk_size or self.settings.rag.chunk_size
        self.chunk_overlap = chunk_overlap or self.settings.rag.chunk_overlap
        
        logger.info(
            f"MainProcessor initialized: "
            f"chunk_size={self.chunk_size}, chunk_overlap={self.chunk_overlap}, "
            f"chunking_strategy={self.settings.rag.chunking_strategy}"
        )
    
    def _get_chunking_params(self) -> Dict[str, Any]:
        """
        Get chunking parameters including strategy and embed_model.
        Thread-safe access to shared embedding model.
        """
        chunking_strategy = self.settings.rag.chunking_strategy
        embed_model = None

        # Only attempt semantic chunking if strategy requires it
        if chunking_strategy in ("semantic", "auto"):
            embed_model = _get_cached_embed_model(self.settings)

            # If model creation failed, fall back to sentence splitting
            if embed_model is None and chunking_strategy == "semantic":
                logger.warning(
                    "Semantic chunking requested but embed_model creation failed. "
                    "Using sentence splitting instead."
                )
                chunking_strategy = "sentence"

        return {
            "strategy": chunking_strategy,
            "embed_model": embed_model,
        }
    
    async def _update_db_status(self, document_id: Optional[UUID], status: ProcessingStatus, error: Optional[str] = None):
        """Helper to update document status in DB if document_id is provided."""
        if not document_id:
            return
            
        try:
            async with async_session_factory() as session:
                repo = DocumentRepository(session)
                await repo.update_status(document_id, status, error)
        except Exception as e:
            logger.error(f"Failed to update DB status for doc {document_id}: {e}")

    async def _update_db_chunk_count(self, document_id: Optional[UUID], count: int):
        """Helper to update chunk count in DB."""
        if not document_id:
            return
            
        try:
            async with async_session_factory() as session:
                repo = DocumentRepository(session)
                await repo.update(document_id, {"chunk_count": count})
        except Exception as e:
            logger.error(f"Failed to update chunk count for doc {document_id}: {e}")

    async def _update_db_preview(self, document_id: Optional[UUID], doc: UnifiedDocument):
        """Helper to update document preview text from first chunk."""
        if not document_id or not doc.chunks:
            return
            
        try:
            # Get first chunk content for preview (truncate to 500 chars)
            preview_text = doc.chunks[0].content[:500] if doc.chunks[0].content else None
            if preview_text:
                async with async_session_factory() as session:
                    repo = DocumentRepository(session)
                    await repo.update(document_id, {"preview": preview_text})
        except Exception as e:
            logger.error(f"Failed to update preview for doc {document_id}: {e}")

    async def _prepare_for_processing(
        self,
        file_path: Path,
        document_type: Optional[DocumentType],
    ) -> DocumentType:
        """Validate file exists and detect document type."""
        if not file_path.exists():
            raise DocumentProcessingError(f"File not found: {file_path}")

        detected_type = document_type or self._detect_document_type(file_path)
        logger.info(
            f"Preparing to process: {file_path.name} (type: {detected_type.value})"
        )
        return detected_type

    async def _process_document_by_type(
        self,
        file_path: Path,
        document_type: DocumentType,
        user_id: Optional[UUID],
        storage_path: Optional[str],
        source_id: Optional[UUID],
        original_filename: Optional[str] = None,
    ) -> UnifiedDocument:
        """Route document to appropriate processor based on type."""
        if document_type == DocumentType.AUDIO:
            return await self._process_audio(file_path, user_id, source_id)
        elif document_type == DocumentType.WEB:
            raise DocumentProcessingError(
                "Use process_url() for web documents, not process_file()"
            )
        else:
            return await self.document_processor.process(
                file_path=file_path,
                user_id=user_id,
                storage_path=storage_path or str(file_path),
                source_id=source_id,
                original_filename=original_filename,
            )

    async def _apply_chunking_if_enabled(
        self,
        doc: UnifiedDocument,
        auto_chunk: bool,
    ) -> UnifiedDocument:
        """Apply chunking strategy if enabled and document has chunks."""
        if not auto_chunk or not doc.chunks:
            return doc

        chunking_params = self._get_chunking_params()
        doc = apply_chunking_to_document_non_destructive(
            doc,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            respect_sentence_boundary=True,
            strategy=chunking_params["strategy"],
            embed_model=chunking_params["embed_model"],
        )
        logger.debug(
            f"Applied chunking (strategy: {chunking_params['strategy']}): "
            f"{doc.chunk_count} chunks"
        )
        return doc

    async def _finalize_processing(
        self,
        doc: UnifiedDocument,
        source_id: Optional[UUID],
        file_path: Path,
    ) -> UnifiedDocument:
        """Validate document and update DB status to completed."""
        self._validate_document(doc)

        # Update DB with chunk count, preview, and status
        await self._update_db_chunk_count(source_id, doc.chunk_count)
        await self._update_db_preview(source_id, doc)
        await self._update_db_status(source_id, ProcessingStatus.COMPLETED)

        logger.info(
            f"Successfully processed {file_path.name}: "
            f"{doc.chunk_count} chunks, status={doc.status.value}"
        )
        return doc

    async def process_file(
        self,
        file_path: Union[str, Path],
        user_id: Optional[UUID] = None,
        storage_path: Optional[str] = None,
        source_id: Optional[UUID] = None,
        document_type: Optional[DocumentType] = None,
        auto_chunk: bool = True,
        original_filename: Optional[str] = None,
    ) -> UnifiedDocument:
        """
        Process a file and return a UnifiedDocument.
        Updates DB status if source_id (document_id) is provided.
        
        Args:
            original_filename: The real filename from the DB. When processing
                temp files downloaded from storage, the temp file has a random
                name (e.g. tmphxad5tz0.docx). Pass the real name here so it
                gets stored in the UnifiedDocument and vector index metadata.
        """
        file_path = Path(file_path)

        # 1. Update DB -> PROCESSING
        await self._update_db_status(source_id, ProcessingStatus.PROCESSING)

        try:
            # 2. Prepare and validate
            detected_type = await self._prepare_for_processing(
                file_path, document_type
            )

            # 3. Process document based on type
            doc = await self._process_document_by_type(
                file_path=file_path,
                document_type=detected_type,
                user_id=user_id,
                storage_path=storage_path,
                source_id=source_id,
                original_filename=original_filename,
            )

            # 4. Apply chunking if enabled
            doc = await self._apply_chunking_if_enabled(doc, auto_chunk)

            # 5. Finalize and update DB
            return await self._finalize_processing(doc, source_id, file_path)

        except Exception as e:
            # Update DB -> FAILED
            await self._update_db_status(source_id, ProcessingStatus.FAILED, str(e))
            raise e
    
    async def process_url(
        self,
        url: str,
        user_id: Optional[UUID] = None,
        source_id: Optional[UUID] = None,
        auto_chunk: bool = True,
    ) -> UnifiedDocument:
        """
        Process a web URL and return a UnifiedDocument.
        """
        await self._update_db_status(source_id, ProcessingStatus.PROCESSING)
        
        try:
            logger.info(f"Processing URL: {url} (user: {user_id})")
            
            # Process web URL
            doc = self.web_processor.process_url(url)
            
            # Update user_id if provided
            if user_id:
                doc.user_id = user_id
            
            # Update document ID if provided
            if source_id:
                doc.id = source_id
            
            # Apply chunking if requested
            if auto_chunk and doc.chunks:
                doc = apply_chunking_to_document_non_destructive(
                    doc,
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                    respect_sentence_boundary=True,
                )
                logger.debug(f"Applied chunking: {doc.chunk_count} chunks")
            
            # Validate document structure
            self._validate_document(doc)
            
            await self._update_db_chunk_count(source_id, doc.chunk_count)
            await self._update_db_preview(source_id, doc)
            await self._update_db_status(source_id, ProcessingStatus.COMPLETED)

            logger.info(
                f"Successfully processed URL {url}: "
                f"{doc.chunk_count} chunks, status={doc.status.value}"
            )
            
            return doc
        except Exception as e:
            await self._update_db_status(source_id, ProcessingStatus.FAILED, str(e))
            raise e
    
    async def process_youtube(
        self,
        youtube_url: str,
        user_id: Optional[UUID] = None,
        source_id: Optional[UUID] = None,
        auto_chunk: bool = True,
    ) -> UnifiedDocument:
        """
        Process a YouTube video and return a UnifiedDocument.
        """
        await self._update_db_status(source_id, ProcessingStatus.PROCESSING)
        
        try:
            logger.info(f"Processing YouTube URL: {youtube_url}")
            
            # Process YouTube video
            doc = await self.youtube_processor.process_video(youtube_url, cleanup_audio=True)
            
            # Update user_id if provided
            if user_id:
                doc.user_id = user_id
            
            # Update document ID if provided
            if source_id:
                doc.id = source_id
            
            # Apply chunking if requested
            if auto_chunk and doc.chunks:
                chunking_params = self._get_chunking_params()
                doc = apply_chunking_to_document_non_destructive(
                    doc,
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                    respect_sentence_boundary=True,
                    strategy=chunking_params["strategy"],
                    embed_model=chunking_params["embed_model"],
                )
                logger.debug(f"Applied chunking (strategy: {chunking_params['strategy']}): {doc.chunk_count} chunks")
            
            # Validate document structure
            self._validate_document(doc)
            
            await self._update_db_chunk_count(source_id, doc.chunk_count)
            await self._update_db_preview(source_id, doc)
            await self._update_db_status(source_id, ProcessingStatus.COMPLETED)

            logger.info(
                f"Successfully processed YouTube video: "
                f"{doc.chunk_count} chunks, status={doc.status.value}"
            )
            
            return doc
        except Exception as e:
            await self._update_db_status(source_id, ProcessingStatus.FAILED, str(e))
            raise e
    
    async def process_gdrive(
        self,
        file_id: str,
        user_id: UUID,
        source_id: Optional[UUID] = None,
        auto_chunk: bool = True,
    ) -> UnifiedDocument:
        """
        Process a file from Google Drive and return a UnifiedDocument.
        
        Args:
            file_id: The Google Drive file ID
            user_id: The user's UUID (required for authentication)
            source_id: Optional document ID for DB tracking
            auto_chunk: Whether to apply chunking
            
        Returns:
            UnifiedDocument with processed content
        """
        await self._update_db_status(source_id, ProcessingStatus.PROCESSING)
        
        try:
            logger.info(f"Processing Google Drive file: {file_id} (user: {user_id})")
            
            # Process Google Drive file
            doc = await self.gdrive_processor.process_file(
                file_id=file_id,
                user_id=user_id,
                source_id=source_id,
            )
            
            # Update user_id if provided
            if user_id:
                doc.user_id = user_id
            
            # Update document ID if provided
            if source_id:
                doc.id = source_id
            
            # Apply chunking if requested
            if auto_chunk and doc.chunks:
                chunking_params = self._get_chunking_params()
                doc = apply_chunking_to_document_non_destructive(
                    doc,
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                    respect_sentence_boundary=True,
                    strategy=chunking_params["strategy"],
                    embed_model=chunking_params["embed_model"],
                )
                logger.debug(f"Applied chunking: {doc.chunk_count} chunks")
            
            # Validate document structure
            self._validate_document(doc)
            
            await self._update_db_chunk_count(source_id, doc.chunk_count)
            await self._update_db_preview(source_id, doc)
            await self._update_db_status(source_id, ProcessingStatus.COMPLETED)

            logger.info(
                f"Successfully processed Google Drive file: "
                f"{doc.chunk_count} chunks, status={doc.status.value}"
            )
            
            return doc
        except Exception as e:
            await self._update_db_status(source_id, ProcessingStatus.FAILED, str(e))
            raise e
    
    async def process_batch(
        self,
        file_paths: List[Union[str, Path]],
        user_id: Optional[UUID] = None,
        auto_chunk: bool = True,
    ) -> List[UnifiedDocument]:
        """
        Process multiple files in batch.
        """
        results: List[UnifiedDocument] = []
        
        logger.info(f"Processing batch of {len(file_paths)} files")
        
        for file_path in file_paths:
            try:
                # Note: process_batch usually doesn't have individual source_ids passed in 
                # unless we change the signature. For now, it won't update DB status.
                doc = await self.process_file(
                    file_path=file_path,
                    user_id=user_id,
                    auto_chunk=auto_chunk,
                )
                results.append(doc)
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}", exc_info=True)
                continue
        
        logger.info(f"Batch processing complete: {len(results)}/{len(file_paths)} successful")
        
        return results
    
    async def _process_audio(
        self,
        file_path: Path,
        user_id: Optional[UUID],
        source_id: Optional[UUID],
    ) -> UnifiedDocument:
        """Process audio file."""
        if not self.settings.assemblyai.api_key:
            raise DocumentProcessingError(
                "AssemblyAI API key not configured. Set ASSEMBLYAI__API_KEY environment variable."
            )
        
        # FIXED: Added await here
        doc = await self.audio_processor.transcribe_audio(
            audio_path=str(file_path),
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        
        if user_id:
            doc.user_id = user_id
        if source_id:
            doc.id = source_id
        
        return doc
    
    def _detect_document_type(self, file_path: Path) -> DocumentType:
        """Detect document type from file extension."""
        ext = file_path.suffix.lower()
        
        ext_map = {
            '.pdf': DocumentType.PDF,
            '.txt': DocumentType.TXT,
            '.doc': DocumentType.DOCX,
            '.docx': DocumentType.DOCX,
            '.md': DocumentType.MARKDOWN,
            '.mp3': DocumentType.AUDIO,
            '.wav': DocumentType.AUDIO,
            '.m4a': DocumentType.AUDIO,
            '.aac': DocumentType.AUDIO,
            '.ogg': DocumentType.AUDIO,
            '.flac': DocumentType.AUDIO,
            '.mp4': DocumentType.VIDEO,
            '.mov': DocumentType.VIDEO,
            '.avi': DocumentType.VIDEO,
        }
        
        return ext_map.get(ext, DocumentType.UNKNOWN)
    
    def _validate_document(self, doc: UnifiedDocument) -> None:
        """
        Validate that a UnifiedDocument has proper structure.
        """
        if not doc.chunks:
            logger.warning(f"Document {doc.id} has no chunks")
            return
        
        for idx, chunk in enumerate(doc.chunks):
            if not chunk.content or not chunk.content.strip():
                logger.warning(f"Document {doc.id} has empty chunk at index {idx}")
            
            if chunk.document_id != doc.id:
                raise DocumentProcessingError(
                    f"Chunk {chunk.chunk_id} has mismatched document_id: "
                    f"expected {doc.id}, got {chunk.document_id}"
                )
            
            if chunk.chunk_index != idx:
                logger.warning(
                    f"Chunk {chunk.chunk_id} has mismatched chunk_index: "
                    f"expected {idx}, got {chunk.chunk_index}"
                )

# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Accessor
# ═══════════════════════════════════════════════════════════════════════════════
@lru_cache(maxsize=1)
def get_main_processor() -> MainProcessor:
    """
    Get the singleton instance of MainProcessor.
    """
    return MainProcessor()

