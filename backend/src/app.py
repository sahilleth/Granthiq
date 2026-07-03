import sys
import os
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

# Fix Windows multiprocessing issue with Langfuse (must be set before any Langfuse imports)
os.environ.setdefault("LANGFUSE_SDK_DISABLE_MULTIPROCESSING", "1")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Add src to path
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from src.config import get_settings
from src.routers.router import api_router
from src.services.observability.langfuse_config import setup_langfuse, flush_langfuse
from src.middleware.correlation import CorrelationIDMiddleware
from src.services.queue.app import proc_app, QUEUE_CRITICAL, QUEUE_HIGH, QUEUE_STANDARD
from src.services.queue.config import queue_settings
from src.services.chat.service import warmup_heavy_components
from src.utils.logger import setup_logger
from src.utils.cache import start_all_caches, stop_all_caches, get_all_cache_stats
from src.db.vector_store import get_vector_store
from src.services.embeddings.embedding_config import (
    configure_llamaindex_embed_model,
    get_llamaindex_embed_model,
)
from src.services.reranker.reranker import get_reranker


async def warmup_all_components():
    """
    Comprehensive warmup of all heavy components.
    Called during startup to pre-load models and initialize caches.
    """
    logger.info("Starting comprehensive component warmup...")

    try:
        # 1. Start all cache cleanup tasks
        await start_all_caches()
        logger.info("✓ Cache systems initialized")

        # 2. Pre-load embedding model (CPU-bound, run in thread)
        await asyncio.to_thread(configure_llamaindex_embed_model)
        embed_model = await asyncio.to_thread(get_llamaindex_embed_model)
        logger.info(f"✓ Embedding model warmed up: {type(embed_model).__name__}")

        # 3. Initialize vector store (includes BM42 sparse model)
        vs = await asyncio.to_thread(get_vector_store)
        logger.info(f"✓ Vector store warmed up: collection={vs.collection_name}")

        # 4. Initialize reranker
        reranker = await asyncio.to_thread(get_reranker)
        if reranker:
            logger.info("✓ Reranker warmed up")

        # 5. Log cache stats
        stats = get_all_cache_stats()
        for cache_stat in stats:
            logger.debug(
                f"Cache '{cache_stat['name']}': size={cache_stat['size']}/{cache_stat['max_size']}"
            )

        logger.info("✓ All components warmed up successfully")

    except Exception as e:
        logger.error(f"Component warmup failed: {e}", exc_info=True)
        # Don't fail startup - just log the error
        # First request will be slower but app remains functional


async def shutdown_all_components():
    """
    Graceful shutdown of all components.
    Called during application shutdown.
    """
    logger.info("Shutting down components...")

    try:
        # Stop all cache cleanup tasks
        await stop_all_caches()
        logger.info("✓ Cache systems stopped")
    except Exception as e:
        logger.warning(f"Error during component shutdown: {e}")


# Configure Loguru first
setup_logger()


# --- Setup Logging (Intercept Uvicorn) ---
class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging():
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()]

    # Suppress noisy libraries
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)


setup_logging()

settings = get_settings()
ENABLE_EMBEDDED_WORKER = os.getenv("ENABLE_EMBEDDED_WORKER", "true").lower() == "true"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"] if settings.api.enable_rate_limiting else [],
    storage_uri="memory://",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """

    logger.info("Application startup...")

    # Initialize Observability
    try:
        setup_langfuse()
        logger.info("✓ Langfuse initialized")
    except Exception as e:
        logger.warning(f"Langfuse init failed: {e}")

    # Pre-warm all heavy components (vector store, embeddings, BM42 sparse model, caches)
    # Run in the background to avoid blocking startup (prevents liveness probe failures)
    # Can be disabled on resource-constrained environments (Railway/Render)
    if os.getenv("SKIP_WARMUP", "false").lower() == "true":
        logger.warning(
            "Skipping heavy component warmup (SKIP_WARMUP=true). First request will be slower."
        )
    else:

        async def _background_warmup():
            try:
                logger.info("Starting background warmup of heavy components...")
                # Use new comprehensive warmup function
                await warmup_all_components()
                logger.info("✓ Heavy components warmed up (background)")
            except Exception as e:
                logger.warning(f"Heavy component warmup failed: {e}")

        # Fire and forget - doesn't block startup
        asyncio.create_task(_background_warmup())

    # 2. Initialize Procrastinate App (always needed for task deferring)
    # Import tasks to register them
    import src.services.queue.tasks

    # Open the app context - required for deferring tasks even without embedded worker
    try:
        await proc_app.open_async()
        logger.info("✓ Procrastinate app opened")
    except Exception as e:
        logger.error(f"⚠ Procrastinate app failed to open: {e}")
        logger.warning(
            "Task queue will be unavailable. API endpoints will still work but background tasks will fail."
        )

    # 3. Start Embedded Worker (only if enabled)
    worker_task = None
    if ENABLE_EMBEDDED_WORKER:
        logger.info("Starting embedded Procrastinate worker...")

        async def _run_worker():
            try:
                await proc_app.run_worker_async(
                    queues=[QUEUE_CRITICAL, QUEUE_HIGH, QUEUE_STANDARD],
                    concurrency=queue_settings.workers_critical
                    + queue_settings.workers_high,
                    listen_notify=False,  # Critical for Windows/Supabase
                    wait=True,
                )
            except asyncio.CancelledError:
                logger.info("Worker task cancelled")
            except Exception as e:
                logger.error("Worker failed: {}", e)

        worker_task = asyncio.create_task(_run_worker())
        logger.info("✓ Embedded worker task started")
    else:
        logger.info(
            "Embedded worker disabled (ENABLE_EMBEDDED_WORKER=false). Use a separate worker process."
        )

    yield

    # 4. Shutdown
    logger.info("Application shutting down...")

    # Stop embedded worker if running
    if worker_task:
        logger.info("Stopping embedded worker...")
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass  # Expected
        except Exception as e:
            logger.warning(f"Error stopping worker task: {e}")

    # Always close Procrastinate app (we always open it)
    try:
        await proc_app.close_async()
        logger.info("✓ Procrastinate app closed")
    except Exception as e:
        logger.warning(f"Error closing Procrastinate app: {e}")

    # Flush traces
    try:
        flush_langfuse()
    except Exception as e:
        logger.warning(f"Error flushing Langfuse: {e}")

    # Stop all components
    try:
        await shutdown_all_components()
    except Exception as e:
        logger.warning(f"Error during component shutdown: {e}")

    # Close DB
    from src.db.session import engine

    await engine.dispose()
    logger.info("✓ Shutdown complete")


def create_app() -> FastAPI:
    # Initialize Sentry
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn and str(sentry_dsn).lower() not in ("none", "null", "", "undefined"):
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.asyncio import AsyncioIntegration
            from sentry_sdk.integrations.logging import LoggingIntegration

            sentry_logging = LoggingIntegration(
                level=logging.INFO, event_level=logging.ERROR
            )

            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=os.getenv("ENVIRONMENT", "development"),
                traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1.0")),
                profiles_sample_rate=float(
                    os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "1.0")
                ),
                integrations=[
                    FastApiIntegration(),
                    AsyncioIntegration(),
                    sentry_logging,
                ],
                send_default_pii=False,
            )
            logger.info("✓ Sentry initialized successfully")
        except Exception as e:
            logger.warning(f"⚠ Failed to initialize Sentry: {e}")

    app = FastAPI(
        title="Granthiq API",
        version="1.0.0",
        lifespan=lifespan,
        redirect_slashes=False,  # Prevent 307 redirects on trailing slash mismatches
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Add standardized error response handler
    from fastapi import HTTPException
    from src.utils.errors import error_exception_handler

    app.add_exception_handler(HTTPException, error_exception_handler)

    app.add_middleware(CorrelationIDMiddleware)

    # Security headers middleware (production only)
    if settings.environment == "production":
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request as StarletteRequest
        from starlette.responses import Response as StarletteResponse

        class SecurityHeadersMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: StarletteRequest, call_next):
                response: StarletteResponse = await call_next(request)
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                response.headers["Permissions-Policy"] = (
                    "camera=(), microphone=(), geolocation=()"
                )
                # HSTS only on HTTPS
                if request.url.scheme == "https":
                    response.headers["Strict-Transport-Security"] = (
                        "max-age=31536000; includeSubDomains"
                    )
                return response

        app.add_middleware(SecurityHeadersMiddleware)

    # CORS: explicit methods/headers in production, permissive in development
    if settings.environment == "production":
        cors_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
        cors_headers = ["Authorization", "Content-Type", "X-Correlation-ID", "Accept"]
    else:
        cors_methods = ["*"]
        cors_headers = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_origin_regex=r"https://.*\.granthiq\.xyz|https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=cors_methods,
        allow_headers=cors_headers,
    )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    # CRITICAL: Railway and other PaaS provide a dynamic PORT
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
