import asyncio
import sys
from pathlib import Path
from loguru import logger
from datetime import datetime, timedelta

# Fix for psycopg async support on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add backend directory to path
_backend_dir = Path(__file__).parent.parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from src.services.queue.app import proc_app, QUEUE_CRITICAL, QUEUE_HIGH, QUEUE_STANDARD
from src.services.queue.config import queue_settings
from src.db.session import async_session_factory
from src.db.repositories.document import DocumentRepository
from src.db.repositories.content import ContentRepository
from src.db.models import ProcessingStatus
from datetime import datetime, timedelta, timezone


async def recover_dead_jobs_with_retry(
    max_retries: int = 3, initial_delay: float = 2.0
):
    """
    Dead Job Recovery with retry logic for resilient startup.
    """
    if not queue_settings.enable_dead_job_recovery:
        logger.info("Dead job recovery is disabled")
        return

    threshold_minutes = queue_settings.dead_job_threshold_minutes
    threshold_time = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)

    logger.info(
        f"Running dead job recovery (threshold: {threshold_minutes} minutes)..."
    )

    last_error = None
    delay = initial_delay

    for attempt in range(1, max_retries + 1):
        try:
            async with async_session_factory() as session:
                doc_repo = DocumentRepository(session)
                content_repo = ContentRepository(session)

                doc_count = await doc_repo.reset_stuck_to_failed(
                    threshold_time=threshold_time,
                    error_message=f"Worker crashed during processing (recovered at startup)",
                )
                if doc_count > 0:
                    logger.warning(f"  Reset {doc_count} stuck document(s) to FAILED")

                content_count = await content_repo.reset_stuck_to_failed(
                    threshold_time=threshold_time,
                    error_message=f"Worker crashed during generation (recovered at startup)",
                )
                if content_count > 0:
                    logger.warning(
                        f"  Reset {content_count} stuck content record(s) to FAILED"
                    )

                total_recovered = doc_count + content_count
                if total_recovered > 0:
                    logger.info(
                        f"  Dead job recovery complete: {total_recovered} job(s) reset to FAILED"
                    )
                else:
                    logger.info("  Dead job recovery complete: No stuck jobs found")

                return

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"  Dead job recovery attempt {attempt} failed: {repr(e)}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
                delay *= 2
            else:
                logger.error(
                    f"  Dead job recovery failed after {max_retries} attempts: {repr(e)}"
                )


def main():
    """
    Main worker entry point.

    Starts the Procrastinate worker with configured concurrency settings.
    """

    logger.info(" Starting Procrastinate Worker")

    # Log configuration
    logger.info(f"Workers Configuration:")
    logger.info(f"   CRITICAL queue: {queue_settings.workers_critical} workers")
    logger.info(f"   HIGH queue: {queue_settings.workers_high} workers")
    logger.info(f"   STANDARD queue: {queue_settings.workers_standard} workers")
    logger.info(f"Retry Configuration:")
    logger.info(f"   CRITICAL tasks: {queue_settings.retry_attempts_critical} retries")
    logger.info(f"   HIGH tasks: {queue_settings.retry_attempts_high} retries")
    logger.info(f"   STANDARD tasks: {queue_settings.retry_attempts_standard} retries")

    # Run dead job recovery
    logger.info("\n" + "=" * 60)
    try:
        asyncio.run(recover_dead_jobs_with_retry(max_retries=3, initial_delay=2.0))
    except Exception as e:
        logger.error(f"Dead job recovery failed: {repr(e)}", exc_info=True)

    # Import tasks to register them
    import src.services.queue.tasks  # noqa

    # Start the worker
    # This will block and listen for jobs
    try:
        proc_app.run_worker(
            queues=[QUEUE_CRITICAL, QUEUE_HIGH, QUEUE_STANDARD],
            concurrency=queue_settings.workers_critical
            + queue_settings.workers_high
            + queue_settings.workers_standard,
            listen_notify=False,
            fetch_job_polling_interval=2.0,
        )
    except KeyboardInterrupt:
        logger.info(" Worker stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Worker crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
