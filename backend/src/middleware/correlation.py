import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from loguru import logger
from typing import Optional


_correlation_id_ctx_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> Optional[str]:
    """
    Get the current request's correlation ID.

    Returns:
        str: Correlation ID if available, None otherwise

    Example:
        from src.middleware.correlation import get_correlation_id

        correlation_id = get_correlation_id()
        logger.info(f"[{correlation_id}] Processing request")
    """
    return _correlation_id_ctx_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID for current context (internal use)."""
    _correlation_id_ctx_var.set(correlation_id)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add correlation IDs to all requests.

    How it works:
    1. Checks for existing X-Correlation-ID header (from clients/upstream)
    2. If not found, generates new UUID
    3. Stores ID in request state and context variable
    4. Adds ID to response headers
    5. Logs request with correlation ID

    Benefits:
    - Trace requests across distributed systems
    - Debug production issues with specific request IDs
    - Link logs across multiple services
    - Client can pass correlation ID for end-to-end tracing
    """

    CORRELATION_ID_HEADER = "X-Correlation-ID"

    async def dispatch(self, request: Request, call_next):
        """Process request and add correlation ID."""
        print(f"[MIDDLEWARE] Request: {request.method} {request.url.path}", flush=True)

        # Get or generate correlation ID
        correlation_id = request.headers.get(
            self.CORRELATION_ID_HEADER,
            str(uuid.uuid4())
        )

        # Store in request state (for route handlers)
        request.state.correlation_id = correlation_id

        # Store in context variable (for services/utilities)
        set_correlation_id(correlation_id)

        # Log request with correlation ID
        logger.info(
            f"[{correlation_id}] {request.method} {request.url.path} "
            f"- Client: {request.client.host if request.client else 'unknown'}"
        )

        try:
            # Process request
            response: Response = await call_next(request)
            print(f"[MIDDLEWARE] Response: {response.status_code} for {request.url.path}", flush=True)

            # Add correlation ID to response headers
            response.headers[self.CORRELATION_ID_HEADER] = correlation_id

            # Log response with correlation ID
            logger.info(
                f"[{correlation_id}] Response: {response.status_code} "
                f"- {request.method} {request.url.path}"
            )

            return response

        except Exception as e:
            # Log errors with correlation ID
            logger.error(
                "[{}] Error processing request: {}",
                correlation_id,
                e,
                exc_info=True
            )
            raise

        finally:
            # Clear context (important for async contexts)
            set_correlation_id(None)


class CorrelationIDLoggerFilter:
    """
    Loguru filter to automatically add correlation ID to all log records.

    Usage in logging setup:
        from loguru import logger
        from src.middleware.correlation import CorrelationIDLoggerFilter

        # Remove default logger
        logger.remove()

        # Add logger with correlation ID
        logger.add(
            sys.stderr,
            format="{time} | {level} | [{extra[correlation_id]}] | {message}",
            filter=CorrelationIDLoggerFilter()
        )

    This will automatically include correlation ID in all logs:
        2024-01-13 10:30:00 | INFO | [abc-123-def] | Processing user request
    """

    def __call__(self, record):
        """Add correlation ID to log record."""
        correlation_id = get_correlation_id()
        record["extra"]["correlation_id"] = correlation_id or "no-correlation-id"
        return True


# Utility functions for manual correlation ID management

def with_correlation_id(correlation_id: str):
    """
    Context manager to temporarily set correlation ID.

    Useful for background tasks or async operations that don't
    originate from an HTTP request.

    Usage:
        from src.middleware.correlation import with_correlation_id

        async def background_task():
            with with_correlation_id("bg-task-123"):
                # All logs in this context will have correlation_id="bg-task-123"
                logger.info("Processing background task")
    """
    class CorrelationIDContext:
        def __enter__(self):
            self.token = _correlation_id_ctx_var.set(correlation_id)
            return self

        def __exit__(self, *args):
            _correlation_id_ctx_var.reset(self.token)

    return CorrelationIDContext()


async def async_with_correlation_id(correlation_id: str):
    """
    Async context manager to temporarily set correlation ID.

    Usage:
        from src.middleware.correlation import async_with_correlation_id

        async def background_task():
            async with async_with_correlation_id("bg-task-123"):
                # All logs in this context will have correlation_id="bg-task-123"
                logger.info("Processing background task")
    """
    class AsyncCorrelationIDContext:
        async def __aenter__(self):
            self.token = _correlation_id_ctx_var.set(correlation_id)
            return self

        async def __aexit__(self, *args):
            _correlation_id_ctx_var.reset(self.token)

    return AsyncCorrelationIDContext()
