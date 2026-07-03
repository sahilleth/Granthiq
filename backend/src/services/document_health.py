
from datetime import datetime, timedelta, timezone
from loguru import logger


from src.db.models import Document, ProcessingStatus
from src.db.repositories.document import DocumentRepository
from src.db.session import async_session_factory
from src.config import get_settings
from sqlmodel import select
STUCK_DOCUMENT_THRESHOLD_HOURS = 1  # Consider documents stuck if pending > 1 hour

async def check_stuck_documents() -> int:
    settings = get_settings()
    threshold_time = datetime.now(timezone.utc) - timedelta(hours=STUCK_DOCUMENT_THRESHOLD_HOURS)
    
    async with async_session_factory() as session:
        repo = DocumentRepository(session)
        
        statement = (
            select(Document)
            .where(Document.status == ProcessingStatus.PENDING)
            .where(Document.created_at < threshold_time)
        )
        
        result = await session.exec(statement)
        stuck_docs = result.all()
        
        if not stuck_docs:
            logger.info("No stuck documents found")
            return 0
        
        logger.warning(f"Found {len(stuck_docs)} stuck documents (pending > {STUCK_DOCUMENT_THRESHOLD_HOURS} hours)")
        
        failed_count = 0
        for doc in stuck_docs:
            try:
                await repo.update_status(
                    doc.id,
                    ProcessingStatus.FAILED,
                    f"Document processing timed out. Status was PENDING for more than {STUCK_DOCUMENT_THRESHOLD_HOURS} hours. "
                    "This may indicate the background processing task was interrupted or failed."
                )
                failed_count += 1
                logger.info(f"Marked stuck document {doc.id} as FAILED")
            except Exception as e:
                logger.error(f"Failed to mark document {doc.id} as failed: {e}")
        
        logger.info(f"Marked {failed_count} stuck documents as FAILED")
        return failed_count

async def startup_health_check():
    try:
        logger.info("Running startup health check for stuck documents...")
        failed_count = await check_stuck_documents()
        if failed_count > 0:
            logger.warning(f"Startup check: {failed_count} documents were marked as FAILED due to timeout")
        else:
            logger.info("Startup check: No stuck documents found")
    except Exception as e:
        logger.error(f"Startup health check failed: {e}", exc_info=True)
