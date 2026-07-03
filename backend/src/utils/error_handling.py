"""
Centralized error handling utilities.
Provides consistent logging for non-critical error scenarios.
"""

import logging
from typing import Optional, Callable, Any
from functools import wraps

logger = logging.getLogger(__name__)


def safe_execute(
    operation: Callable[[], Any],
    error_message: str,
    default_return: Any = None,
    log_level: str = "warning",
    exc_info: bool = False
) -> Any:
    """
    Execute an operation with standardized error handling.

    Args:
        operation: Callable to execute
        error_message: Message to log on failure
        default_return: Value to return on failure
        log_level: Logging level (debug, info, warning, error)
        exc_info: Whether to include exception traceback

    Returns:
        Operation result or default_return on failure
    """
    try:
        return operation()
    except Exception as e:
        log_func = getattr(logger, log_level)
        log_func(f"{error_message}: {type(e).__name__}: {e}", exc_info=exc_info)
        return default_return


def safe_cleanup(
    cleanup_func: Callable[[], None],
    resource_name: str
) -> None:
    """
    Execute cleanup code with proper error logging.

    Args:
        cleanup_func: Cleanup operation
        resource_name: Name of resource being cleaned up (for logging)
    """
    try:
        cleanup_func()
    except FileNotFoundError:
        pass  # Already deleted, OK
    except PermissionError as e:
        logger.warning(f"Permission denied cleaning up {resource_name}: {e}")
    except Exception as e:
        logger.warning(f"Cleanup failed for {resource_name}: {type(e).__name__}: {e}")


def log_exceptions(
    error_message: str,
    log_level: str = "error",
    exc_info: bool = True
):
    """
    Decorator for logging exceptions in functions.

    Usage:
        @log_exceptions("Database update failed")
        def update_record(data):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                log_func = getattr(logger, log_level)
                log_func(f"{error_message}: {type(e).__name__}: {e}", exc_info=exc_info)
                raise
        return wrapper
    return decorator
