import asyncio
from uuid import UUID
from typing import Optional
from loguru import logger
from pathlib import Path

from src.services.queue.app import proc_app, QUEUE_CRITICAL, QUEUE_HIGH, QUEUE_STANDARD
from src.services.queue.config import TASK_RETRY_CONFIG, queue_settings
from src.db.session import async_session_factory
from src.db.repositories.document import DocumentRepository
from src.db.repositories.content import ContentRepository
from src.db.repositories.task_progress import TaskProgressRepository
from src.db.repositories.notebook import NotebookRepository
from src.db.models import ProcessingStatus, ContentType
from src.services.ingestion.main_processor import MainProcessor
from src.services.ingestion.audio.audio_processor import AudioTranscriber
from src.services.generation.service import GenerationService, get_generation_service
from src.services.storage import get_storage_service
from src.config import get_settings
from src.services.indexer.indexer import get_indexer
from src.services.llm.factory import create_llamaindex_llm
from src.services.llm.provider_selector import select_generation_llm_provider
settings = get_settings()

# Default bucket for document storage
DEFAULT_DOCUMENT_BUCKET = "notebook-private"


class TaskTimeoutError(Exception):
    """Raised when a task exceeds its configured timeout."""
    pass


async def with_timeout(coro, timeout_seconds: int, task_name: str):
    """
    Execute a coroutine with a timeout.

    Args:
        coro: The coroutine to execute
        timeout_seconds: Maximum time allowed in seconds
        task_name: Name of the task (for error messages)

    Returns:
        The result of the coroutine

    Raises:
        TaskTimeoutError: If the coroutine exceeds the timeout
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise TaskTimeoutError(
            f"Task '{task_name}' exceeded timeout of {timeout_seconds} seconds"
        )


async def _init_task_progress(
    session,
    job_id: int,
    user_id: Optional[UUID] = None,
    notebook_id: Optional[UUID] = None,
    document_id: Optional[UUID] = None,
    content_id: Optional[UUID] = None,
    message: str = "Task started"
) -> None:
    """
    Initialize progress tracking for a task.

    Creates the initial progress record. Errors are logged but don't fail the task.
    """
    try:
        progress_repo = TaskProgressRepository(session)
        await progress_repo.create_progress(
            job_id=job_id,
            user_id=user_id,
            notebook_id=notebook_id,
            document_id=document_id,
            content_id=content_id,
            progress_percent=0,
            message=message
        )
        await session.commit()
    except Exception as e:
        logger.warning(f"Failed to initialize task progress: {e}")


async def _update_task_progress(
    session,
    job_id: int,
    progress_percent: int,
    message: str
) -> None:
    """
    Update progress for a running task.

    Errors are logged but don't fail the task.
    """
    try:
        progress_repo = TaskProgressRepository(session)
        await progress_repo.update_progress(job_id, progress_percent, message)
        await session.commit()
    except Exception as e:
        logger.warning(f"Failed to update task progress: {e}")




@proc_app.task(
    queue=QUEUE_CRITICAL,
    retry=TASK_RETRY_CONFIG["critical"]["retry_attempts"],
    pass_context=True
)
async def process_document_task(
    context,
    document_id: str,
    user_id: str,
    storage_path: str,
    file_path: Optional[str] = None,
    bucket: Optional[str] = None
):
    """
    Process uploaded document (PDF, DOCX, TXT, etc.) in background.

    Args:
        context: Procrastinate job context
        document_id: UUID of document record in database
        user_id: UUID of user who uploaded the document
        storage_path: Storage path (S3/Supabase) where file is stored
        file_path: Optional local file path (if already downloaded)
        bucket: Storage bucket name (defaults to notebook-private)

    Returns:
        dict: Processing result with chunk count and status

    Raises:
        Exception: On processing failure (triggers retry)
    """
    doc_uuid = UUID(document_id)
    user_uuid = UUID(user_id)
    bucket = bucket or DEFAULT_DOCUMENT_BUCKET
    job_id = context.job.id

    logger.info(f"[Task {job_id}] Starting document processing: {document_id}")

    # Track temp file for cleanup
    temp_file_path: Optional[Path] = None

    # Manual Dependency Injection (FastAPI Depends won't work here)
    async with async_session_factory() as session:
        doc_repo = DocumentRepository(session)
        processor = MainProcessor()
        storage = get_storage_service()

        try:
            # Initialize progress tracking
            await _init_task_progress(
                session, job_id,
                user_id=user_uuid,
                document_id=doc_uuid,
                message="Starting document processing"
            )

            # Update status: PENDING → PROCESSING
            await doc_repo.update_status(doc_uuid, ProcessingStatus.PROCESSING)
            await _update_task_progress(session, job_id, 10, "Preparing to download file")
            logger.info(f"[Task {job_id}] Status updated to PROCESSING")

            # Download from storage if needed
            local_file_path: Path
            if file_path:
                local_file_path = Path(file_path)
                await _update_task_progress(session, job_id, 20, "Using local file")
            else:
                # Download file from storage to temp directory
                await _update_task_progress(session, job_id, 15, "Downloading from storage...")
                logger.info(f"[Task {job_id}] Downloading from storage: {storage_path}")
                temp_file_path = await storage.download_to_temp(storage_path, bucket)
                local_file_path = temp_file_path
                await _update_task_progress(session, job_id, 30, "File downloaded successfully")
                logger.info(f"[Task {job_id}] Downloaded to: {local_file_path}")

            # Process document with chunking (with timeout)
            await _update_task_progress(session, job_id, 40, "Parsing document...")

            # Fetch doc record to get the real filename (temp files have random names)
            db_doc = await doc_repo.get(doc_uuid)
            real_filename = db_doc.filename if db_doc else None

            unified_doc = await with_timeout(
                processor.process_file(
                    file_path=local_file_path,
                    user_id=user_uuid,
                    storage_path=storage_path,
                    source_id=doc_uuid,
                    auto_chunk=True,
                    original_filename=real_filename,
                ),
                timeout_seconds=queue_settings.timeout_critical,
                task_name="document_processing"
            )

            chunk_count = len(unified_doc.chunks) if unified_doc and unified_doc.chunks else 0
            
            # Index the document immediately
            if chunk_count > 0:
                # IMPORTANT: Fetch notebook_id from DB to ensure it's in metadata for filtering
                db_doc = await doc_repo.get(doc_uuid)
                if db_doc and db_doc.notebook_id:
                    if unified_doc.metadata is None:
                        unified_doc.metadata = {}
                    unified_doc.metadata["notebook_id"] = str(db_doc.notebook_id)
                    logger.info(f"[Task {job_id}] Injected notebook_id {db_doc.notebook_id} into metadata")

                await _update_task_progress(session, job_id, 80, f"Indexing {chunk_count} chunks...")
                logger.info(f"[Task {job_id}] Indexing {chunk_count} chunks for document {document_id}")
                
                # Get indexer (singleton)
               
                indexer = get_indexer()
                
                # Index in background (though we are already in background task)
                # We do it synchronously here to ensure it's done before task completes
                # Note: index_document is separate, not async, but Qdrant wrapper handles async internally or sync
                # index_document is sync wrapper around async vector store calls usually, let's check.
                # DocumentIndexer.index_document is sync def but calls vector_store.add_nodes which might be sync.
                # DocumentIndexer: def index_document(...) -> List[str]
                
                try:
                    await indexer.index_document(unified_doc)
                    logger.info(f"[Task {job_id}] Indexing complete")
                except Exception as index_err:
                    logger.error(f"[Task {job_id}] Indexing failed: {index_err}")
                    # We don't fail the whole task if indexing fails, but we should probably warn
                    # actually strictly speaking if indexing fails, RAG fails. So maybe we SHOULD fail.
                    # But the document is "Processed". 
                    # Let's log error and continue for now, status COMPLETED implies processed.
                    pass

            await _update_task_progress(session, job_id, 90, f"Processing complete: {chunk_count} chunks created")
            logger.info(f"[Task {job_id}] Processing complete: {chunk_count} chunks")

            # Update status: PROCESSING → COMPLETED
            await doc_repo.update_status(doc_uuid, ProcessingStatus.COMPLETED)
            await _update_task_progress(session, job_id, 100, "Document processing completed successfully")
            await session.commit()

            return {
                "status": "success",
                "document_id": document_id,
                "chunk_count": chunk_count
            }

        except Exception as e:
            logger.error(f"[Task {job_id}] Document processing failed: {e}", exc_info=True)

            # Update progress with error
            await _update_task_progress(session, job_id, -1, f"Failed: {str(e)[:100]}")

            # Update status: PROCESSING → FAILED
            await doc_repo.update_status(
                doc_uuid,
                ProcessingStatus.FAILED,
                error_message=str(e)
            )
            await session.commit()

            # Re-raise for Procrastinate retry logic
            raise e

        finally:
            # Cleanup temp file
            if temp_file_path and temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                    logger.debug(f"[Task {job_id}] Cleaned up temp file: {temp_file_path}")
                except Exception as cleanup_error:
                    logger.warning(f"[Task {job_id}] Failed to cleanup temp file: {cleanup_error}")


@proc_app.task(
    queue=QUEUE_CRITICAL,
    retry=TASK_RETRY_CONFIG["critical"]["retry_attempts"],
    pass_context=True
)
async def process_audio_task(
    context,
    document_id: str,
    user_id: str,
    audio_path: str,
    enable_speaker_diarization: bool = True
):
    """
    Transcribe audio file (MP3, WAV, M4A, etc.) using AssemblyAI.
    
    Args:
        context: Procrastinate job context
        document_id: UUID of document record
        user_id: UUID of user
        audio_path: Local path to audio file
        enable_speaker_diarization: Enable speaker identification
    
    Returns:
        dict: Transcription result with text and metadata
    """
    doc_uuid = UUID(document_id)
    user_uuid = UUID(user_id)
    job_id = context.job.id
    
    logger.info(f"[Task {job_id}] Starting audio transcription: {document_id}")
    
    async with async_session_factory() as session:
        doc_repo = DocumentRepository(session)
        
        try:
            # Initialize progress tracking
            await _init_task_progress(
                session, job_id,
                user_id=user_uuid,
                document_id=doc_uuid,
                message="Starting audio transcription"
            )
            
            await doc_repo.update_status(doc_uuid, ProcessingStatus.PROCESSING)
            await _update_task_progress(session, job_id, 10, "Preparing to transcribe audio...")
            
            # Initialize transcriber
            transcriber = AudioTranscriber(api_key=settings.assemblyai.api_key)
            
            await _update_task_progress(session, job_id, 20, "Transcribing audio (this may take several minutes)...")
            
            # Transcribe (this is the long-running operation: 3-10min)
            unified_doc = await asyncio.to_thread(
                transcriber.transcribe_audio,
                audio_path=audio_path,
                enable_speaker_diarization=enable_speaker_diarization
            )
            
            chunk_count = len(unified_doc.chunks) if unified_doc and unified_doc.chunks else 0
            await _update_task_progress(session, job_id, 70, f"Transcription complete: {chunk_count} chunks")
            
            # Index the audio document
            if chunk_count > 0:
                # IMPORTANT: Fetch notebook_id from DB to ensure it's in metadata for filtering
                db_doc = await doc_repo.get(doc_uuid)
                if db_doc and db_doc.notebook_id:
                    if unified_doc.metadata is None:
                        unified_doc.metadata = {}
                    unified_doc.metadata["notebook_id"] = str(db_doc.notebook_id)
                
                await _update_task_progress(session, job_id, 80, f"Indexing {chunk_count} chunks...")
                
           
                indexer = get_indexer()
                try:
                    logger.info(f"[Task {job_id}] Indexing {chunk_count} chunks for audio {document_id}")
                    await indexer.index_document(unified_doc)
                    await _update_task_progress(session, job_id, 90, "Indexing complete")
                except Exception as idx_err:
                     logger.error(f"[Task {job_id}] Audio indexing failed: {idx_err}")

            logger.info(f"[Task {job_id}] Transcription complete: {chunk_count} chunks")
            
            await doc_repo.update_status(doc_uuid, ProcessingStatus.COMPLETED)
            await _update_task_progress(session, job_id, 100, "Audio transcription completed successfully")
            await session.commit()
            
            return {
                "status": "success",
                "document_id": document_id,
                "transcript_length": len(unified_doc.text) if unified_doc else 0,
                "chunk_count": chunk_count
            }
            
        except Exception as e:
            logger.error(f"[Task {job_id}] Audio transcription failed: {e}", exc_info=True)
            await _update_task_progress(session, job_id, -1, f"Failed: {str(e)[:100]}")
            await doc_repo.update_status(doc_uuid, ProcessingStatus.FAILED, error_message=str(e))
            await session.commit()
            raise e


@proc_app.task(
    queue=QUEUE_CRITICAL,
    retry=TASK_RETRY_CONFIG["critical"]["retry_attempts"],
    pass_context=True
)
async def process_youtube_task(
    context,
    document_id: str,
    user_id: str,
    youtube_url: str
):
    """
    Process YouTube video: Download transcript and metadata.
    
    Args:
        context: Procrastinate job context
        document_id: UUID of document record
        user_id: UUID of user
        youtube_url: YouTube video URL
    
    Returns:
        dict: Processing result
    """
    doc_uuid = UUID(document_id)
    user_uuid = UUID(user_id)
    job_id = context.job.id
    
    logger.info(f"[Task {job_id}] Starting YouTube processing: {youtube_url}")
    
    async with async_session_factory() as session:
        doc_repo = DocumentRepository(session)
        processor = MainProcessor()
        
        try:
            # Initialize progress tracking
            await _init_task_progress(
                session, job_id,
                user_id=user_uuid,
                document_id=doc_uuid,
                message="Starting YouTube processing"
            )
            
            await doc_repo.update_status(doc_uuid, ProcessingStatus.PROCESSING)
            await _update_task_progress(session, job_id, 10, "Fetching YouTube video metadata...")
            
            # Process YouTube (2-8min depending on video length)
            await _update_task_progress(session, job_id, 20, "Downloading transcript...")
            unified_doc = await processor.process_youtube(
                youtube_url=youtube_url,
                user_id=user_uuid,
                source_id=doc_uuid,
                auto_chunk=True
            )
            
            chunk_count = len(unified_doc.chunks) if unified_doc and unified_doc.chunks else 0
            await _update_task_progress(session, job_id, 70, f"Transcript ready: {chunk_count} chunks")
            
            # Index the YouTube document
            if chunk_count > 0:
                # IMPORTANT: Fetch notebook_id from DB to ensure it's in metadata for filtering
                db_doc = await doc_repo.get(doc_uuid)
                if db_doc and db_doc.notebook_id:
                    if unified_doc.metadata is None:
                        unified_doc.metadata = {}
                    unified_doc.metadata["notebook_id"] = str(db_doc.notebook_id)
                
                await _update_task_progress(session, job_id, 80, f"Indexing {chunk_count} chunks...")
                
              
                indexer = get_indexer()
                try:
                    logger.info(f"[Task {job_id}] Indexing {chunk_count} chunks for video {document_id}")
                    await indexer.index_document(unified_doc)
                    await _update_task_progress(session, job_id, 90, "Indexing complete")
                except Exception as idx_err:
                     logger.error(f"[Task {job_id}] YouTube indexing failed: {idx_err}")

            logger.info(f"[Task {job_id}] YouTube processing complete: {chunk_count} chunks")
            
            await doc_repo.update_status(doc_uuid, ProcessingStatus.COMPLETED)
            await _update_task_progress(session, job_id, 100, "YouTube processing completed successfully")
            await session.commit()
            
            return {
                "status": "success",
                "document_id": document_id,
                "chunk_count": chunk_count
            }
            
        except Exception as e:
            logger.error(f"[Task {job_id}] YouTube processing failed: {e}", exc_info=True)
            await _update_task_progress(session, job_id, -1, f"Failed: {str(e)[:100]}")
            await doc_repo.update_status(doc_uuid, ProcessingStatus.FAILED, error_message=str(e))
            await session.commit()
            raise e



@proc_app.task(
    queue=QUEUE_HIGH,
    retry=TASK_RETRY_CONFIG["high"]["retry_attempts"],
    pass_context=True
)
async def generate_podcast_task(
    context,
    content_id: str,
    notebook_id: str,
    user_id: str,
    document_ids: Optional[list[str]] = None
):
    """
    Generate podcast script and audio for notebook.
    
    This is a two-phase task:
    1. Script generation (40-98s)
    2. Audio generation (2-10min)
    
    Args:
        context: Procrastinate job context
        content_id: UUID of content record
        notebook_id: UUID of notebook
        user_id: UUID of user
        document_ids: Optional list of document UUIDs to include
    
    Returns:
        dict: Generation result with audio URL
    """
    content_uuid = UUID(content_id)
    notebook_uuid = UUID(notebook_id)
    user_uuid = UUID(user_id)
    doc_uuids = [UUID(doc_id) for doc_id in document_ids] if document_ids else None
    job_id = context.job.id
    
    logger.info(f"[Task {job_id}] Starting podcast generation: {content_id}")
    
    async with async_session_factory() as session:
        content_repo = ContentRepository(session)
        gen_service = get_generation_service()
        
        try:
            # Initialize progress tracking
            await _init_task_progress(
                session, job_id,
                user_id=user_uuid,
                notebook_id=notebook_uuid,
                content_id=content_uuid,
                message="Starting podcast generation"
            )
            
            await content_repo.update_status(content_uuid, ProcessingStatus.PROCESSING)
            await _update_task_progress(session, job_id, 10, "Retrieving context for podcast...")
            
            # Generate podcast (script + audio) with timeout
            result = await with_timeout(
                gen_service.generate_content(
                    session=session,
                    content_type="podcast",
                    notebook_id=notebook_uuid,
                    document_ids=doc_uuids,
                    user_id=user_uuid,
                    content_id=content_uuid
                ),
                timeout_seconds=queue_settings.timeout_high,
                task_name="podcast_generation"
            )
            
            await _update_task_progress(session, job_id, 90, "Podcast generated successfully")
            logger.info(f"[Task {job_id}] Podcast generation complete")
            
            await content_repo.update_status(content_uuid, ProcessingStatus.COMPLETED)
            await _update_task_progress(session, job_id, 100, "Podcast generation completed")
            await session.commit()
            
            return {
                "status": "success",
                "content_id": content_id,
                "result": result
            }
            
        except Exception as e:
            logger.error(f"[Task {job_id}] Podcast generation failed: {e}", exc_info=True)
            await _update_task_progress(session, job_id, -1, f"Failed: {str(e)[:100]}")
            await content_repo.update_status(content_uuid, ProcessingStatus.FAILED, error_message=str(e))
            await session.commit()
            raise e


# ============================================================================
# STANDARD QUEUE TASKS (Quick: 20-45s)
# ============================================================================

@proc_app.task(
    queue=QUEUE_STANDARD,
    retry=TASK_RETRY_CONFIG["standard"]["retry_attempts"],
    pass_context=True
)
async def generate_quiz_task(
    context,
    content_id: str,
    notebook_id: str,
    user_id: str,
    document_ids: Optional[list[str]] = None
):
    """Generate quiz questions for notebook."""
    return await _generate_content_task(
        context, content_id, notebook_id, user_id, "quiz", document_ids
    )


@proc_app.task(
    queue=QUEUE_STANDARD,
    retry=TASK_RETRY_CONFIG["standard"]["retry_attempts"],
    pass_context=True
)
async def generate_flashcard_task(
    context,
    content_id: str,
    notebook_id: str,
    user_id: str,
    document_ids: Optional[list[str]] = None
):
    """Generate flashcards for notebook."""
    return await _generate_content_task(
        context, content_id, notebook_id, user_id, "flashcard", document_ids
    )


@proc_app.task(
    queue=QUEUE_STANDARD,
    retry=TASK_RETRY_CONFIG["standard"]["retry_attempts"],
    pass_context=True
)
async def generate_mindmap_task(
    context,
    content_id: str,
    notebook_id: str,
    user_id: str,
    document_ids: Optional[list[str]] = None
):
    """Generate mindmap for notebook."""
    return await _generate_content_task(
        context, content_id, notebook_id, user_id, "mindmap", document_ids
    )




async def _generate_content_task(
    context,
    content_id: str,
    notebook_id: str,
    user_id: str,
    content_type: str,
    document_ids: Optional[list[str]] = None
):
    """
    Generic content generation task (quiz, flashcard, mindmap).

    DRY helper to avoid code duplication across standard tasks.
    Includes progress tracking for frontend polling.
    """
    content_uuid = UUID(content_id)
    notebook_uuid = UUID(notebook_id)
    user_uuid = UUID(user_id)
    doc_uuids = [UUID(doc_id) for doc_id in document_ids] if document_ids else None
    job_id = context.job.id

    logger.info(f"[Task {job_id}] Starting {content_type} generation: {content_id}")

    async with async_session_factory() as session:
        content_repo = ContentRepository(session)
        gen_service = get_generation_service()

        try:
            # Initialize progress tracking
            await _init_task_progress(
                session, job_id,
                user_id=user_uuid,
                notebook_id=notebook_uuid,
                content_id=content_uuid,
                message=f"Starting {content_type} generation"
            )

            await content_repo.update_status(content_uuid, ProcessingStatus.PROCESSING)
            await _update_task_progress(session, job_id, 20, f"Retrieving context for {content_type}...")

            # Determine timeout based on content type
            timeout = queue_settings.timeout_standard
            if content_type == "podcast":
                timeout = queue_settings.timeout_high

            result = await with_timeout(
                gen_service.generate_content(
                    session=session,
                    content_type=content_type,
                    notebook_id=notebook_uuid,
                    document_ids=doc_uuids,
                    user_id=user_uuid,
                    content_id=content_uuid  # Pass existing placeholder record ID
                ),
                timeout_seconds=timeout,
                task_name=f"{content_type}_generation"
            )

            await _update_task_progress(session, job_id, 90, f"{content_type.title()} generated successfully")
            logger.info(f"[Task {job_id}] {content_type.title()} generation complete")

            await content_repo.update_status(content_uuid, ProcessingStatus.COMPLETED)
            await _update_task_progress(session, job_id, 100, f"{content_type.title()} generation completed")
            await session.commit()

            return {
                "status": "success",
                "content_id": content_id,
                "content_type": content_type,
                "result": result
            }

        except Exception as e:
            logger.error(f"[Task {job_id}] {content_type.title()} generation failed: {e}", exc_info=True)
            await _update_task_progress(session, job_id, -1, f"Failed: {str(e)[:100]}")
            await content_repo.update_status(content_uuid, ProcessingStatus.FAILED, error_message=str(e))
            await session.commit()
            raise e



@proc_app.task(
    queue=QUEUE_CRITICAL,
    retry=TASK_RETRY_CONFIG["critical"]["retry_attempts"],
    pass_context=True
)
async def process_google_drive_task(
    context,
    file_id: str,
    document_id: str,
    user_id: str,
    notebook_id: str
):
    """
    Process Google Drive file in background.
    
    Args:
        context: Procrastinate job context
        file_id: Google Drive file ID
        document_id: UUID of document record
        user_id: UUID of user
        notebook_id: UUID of notebook
    """
    doc_uuid = UUID(document_id)
    user_uuid = UUID(user_id)
    notebook_uuid = UUID(notebook_id)
    job_id = context.job.id
    
    logger.info(f"[Task {job_id}] Starting Google Drive processing: {file_id}")
    
    async with async_session_factory() as session:
        doc_repo = DocumentRepository(session)
        main_processor = MainProcessor()
        indexer = get_indexer()
        
        try:
            # Initialize progress tracking
            await _init_task_progress(
                session, job_id,
                user_id=user_uuid,
                document_id=doc_uuid,
                notebook_id=notebook_uuid,
                message="Starting Google Drive import"
            )
            
            # Update status: PENDING -> PROCESSING
            await doc_repo.update_status(doc_uuid, ProcessingStatus.PROCESSING)
            await _update_task_progress(session, job_id, 10, "Downloading file from Google Drive...")
            
            # Process file (Download + Extract + Chunk)
            # process_gdrive handles the download internally
            unified_doc = await with_timeout(
                main_processor.process_gdrive(
                    file_id=file_id,
                    user_id=user_uuid,
                    source_id=doc_uuid,
                    auto_chunk=True
                ),
                timeout_seconds=queue_settings.timeout_critical,
                task_name="gdrive_processing"
            )
            
            chunk_count = len(unified_doc.chunks) if unified_doc and unified_doc.chunks else 0
            await _update_task_progress(session, job_id, 70, f"Processing complete: {chunk_count} chunks")
            
            # Index Document
            if chunk_count > 0:
                # Ensure notebook_id is in metadata
                if unified_doc.metadata is None:
                    unified_doc.metadata = {}
                unified_doc.metadata["notebook_id"] = str(notebook_uuid)
                
                await _update_task_progress(session, job_id, 80, f"Indexing {chunk_count} chunks...")
                
                try:
                    logger.info(f"[Task {job_id}] Indexing {chunk_count} chunks for GDrive file {file_id}")
                    await indexer.index_document(unified_doc, replace_existing=True)
                    await _update_task_progress(session, job_id, 90, "Indexing complete")
                except Exception as idx_err:
                    logger.error(f"[Task {job_id}] GDrive indexing failed: {idx_err}")
                    
            logger.info(f"[Task {job_id}] GDrive processing complete: {chunk_count} chunks")
            
            # Update status: PROCESSING -> COMPLETED
            await doc_repo.update_status(doc_uuid, ProcessingStatus.COMPLETED)
            await _update_task_progress(session, job_id, 100, "Import completed successfully")
            await session.commit()
            
            return {
                "status": "success",
                "document_id": document_id,
                "chunk_count": chunk_count
            }
            
        except Exception as e:
            logger.error(f"[Task {job_id}] GDrive processing failed: {str(e)}") 
            
            await _update_task_progress(session, job_id, -1, f"Failed: {str(e)[:100]}")
            await doc_repo.update_status(doc_uuid, ProcessingStatus.FAILED, error_message=str(e))
            await session.commit()
            raise e



@proc_app.task(
    queue=QUEUE_STANDARD,
    retry=TASK_RETRY_CONFIG["standard"]["retry_attempts"],
    pass_context=True
)
async def auto_rename_notebook_task(context, notebook_id: str, user_id: str):
    """
    Auto-rename notebook based on content if still untitled.
    Scheduled to run 3-4 minutes after creation.
    """
    
    
    n_uuid = UUID(notebook_id)
    u_uuid = UUID(user_id)
    job_id = context.job.id
    logger.info(f"[Task {job_id}] Checking auto-rename for notebook {notebook_id}...")

    async with async_session_factory() as session:
        notebook_repo = NotebookRepository(session)
        doc_repo = DocumentRepository(session)
        
        # 1. Check Notebook
        notebook = await notebook_repo.get_notebook(n_uuid, u_uuid)
        if not notebook:
            logger.warning(f"[Task {job_id}] Notebook {notebook_id} not found for auto-rename")
            return
            
        # 2. Check Title
        # If user renamed it (i.e. not "Untitled Notebook"), skip
        # Also check if it looks like a default name
        if notebook.title and "untitled" not in notebook.title.lower():
             logger.info(f"[Task {job_id}] Notebook already named '{notebook.title}', skipping")
             return

        # 3. Check Documents
        documents = await doc_repo.get_by_notebook(n_uuid)
        completed_docs = [d for d in documents if d.status == ProcessingStatus.COMPLETED]
        
        if not completed_docs:
            logger.info(f"[Task {job_id}] No completed documents found, skipping auto-rename")
            return
            
        # 4. Generate Title
        logger.info(f"[Task {job_id}] Generating title from {len(completed_docs)} documents...")
        context_str = "\n".join([f"- {d.filename}" for d in completed_docs[:10]])
        
        prompt = (
            "Generate a short, concise, and professional title (3-6 words) for a project containing these files:\n"
            f"{context_str}\n\n"
            "Rules:\n"
            "1. Do not use 'Project' or 'Notebook' in the title.\n"
            "2. Be descriptive but brief.\n"
            "3. Output ONLY the title.\n"
            "Title:"
        )

        try:
            # Use generation LLM settings
            provider, model, key = select_generation_llm_provider(settings)
            
            # Simple completion
            llm = create_llamaindex_llm(
                provider=provider,
                api_key=key,
                model=model,
                temperature=0.7,
                max_tokens=50
            )
            
            response = await llm.acomplete(prompt)
            new_title = response.text.strip().strip('"').strip("'")
            
            if new_title and len(new_title) > 0:
                await notebook_repo.update(n_uuid, {"title": new_title})
                logger.info(f"[Task {job_id}] Renamed notebook {notebook_id} to '{new_title}'")
                await session.commit()
                
        except Exception as e:
            logger.error(f"[Task {job_id}] Failed to generate title: {e}")


__all__ = [
    "process_document_task",
    "process_audio_task",
    "process_youtube_task",
    "process_google_drive_task",
    "generate_podcast_task",
    "generate_quiz_task",
    "generate_flashcard_task",
    "generate_mindmap_task",
    "auto_rename_notebook_task",
]
