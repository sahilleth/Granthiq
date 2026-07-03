from typing import TypeVar
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)
from loguru import logger
import httpx
from qdrant_client.http.exceptions import UnexpectedResponse


T = TypeVar('T')


# Common exceptions that should trigger retries
RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.NetworkError,
    ConnectionError,
    TimeoutError,
    UnexpectedResponse,
)


def retry_on_transient_error(
    max_attempts: int = 3,
    initial_wait: float = 1.0,
    max_wait: float = 10.0,
    multiplier: float = 2.0
):
    """
    Decorator for retrying operations on transient errors with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        initial_wait: Initial wait time in seconds before first retry (default: 1.0)
        max_wait: Maximum wait time in seconds between retries (default: 10.0)
        multiplier: Exponential backoff multiplier (default: 2.0)

    Example:
        @retry_on_transient_error(max_attempts=3)
        async def upload_to_storage(file_path: str):
            await storage.upload(file_path)
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=multiplier, min=initial_wait, max=max_wait),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, "WARNING"),
        after=after_log(logger, "INFO"),
        reraise=True
    )


def retry_on_storage_error(max_attempts: int = 3):
    """
    Decorator specifically for storage operations (upload, download, delete).

    Uses optimized retry strategy for storage services:
    - 3 attempts by default
    - Exponential backoff: 1s, 2s, 4s
    - Retries on network and timeout errors

    Example:
        @retry_on_storage_error()
        async def upload_file(file_path: str):
            await storage.upload_stream(file_path)
    """
    return retry_on_transient_error(
        max_attempts=max_attempts,
        initial_wait=1.0,
        max_wait=8.0,
        multiplier=2.0
    )


def retry_on_vector_db_error(max_attempts: int = 2):
    """
    Decorator for Qdrant vector database operations.

    Uses conservative retry strategy:
    - 2 attempts by default (Qdrant is usually fast)
    - Shorter backoff: 0.5s, 1s
    - Retries on connection and unexpected response errors

    Example:
        @retry_on_vector_db_error()
        async def search_vectors(query: list):
            return await qdrant_client.search(query)
    """
    return retry_on_transient_error(
        max_attempts=max_attempts,
        initial_wait=0.5,
        max_wait=2.0,
        multiplier=2.0
    )


def retry_on_llm_error(max_attempts: int = 2):
    """
    Decorator for LLM API calls (Gemini, Groq, OpenAI).

    Uses conservative retry strategy:
    - 2 attempts by default (avoid wasting tokens)
    - Medium backoff: 1s, 2s
    - Retries on network errors (not on API errors like rate limits)

    Example:
        @retry_on_llm_error()
        async def call_llm(prompt: str):
            return await llm.generate(prompt)
    """
    return retry_on_transient_error(
        max_attempts=max_attempts,
        initial_wait=1.0,
        max_wait=4.0,
        multiplier=2.0
    )


def retry_on_database_error(max_attempts: int = 3):
    """
    Decorator for database operations (PostgreSQL).

    Uses standard retry strategy:
    - 3 attempts by default
    - Exponential backoff: 0.5s, 1s, 2s
    - Retries on connection errors

    Example:
        @retry_on_database_error()
        async def create_record(data: dict):
            async with session.begin():
                session.add(Record(**data))
                await session.commit()
    """
    return retry_on_transient_error(
        max_attempts=max_attempts,
        initial_wait=0.5,
        max_wait=4.0,
        multiplier=2.0
    )


# Synchronous versions
def retry_sync_on_transient_error(
    max_attempts: int = 3,
    initial_wait: float = 1.0,
    max_wait: float = 10.0,
    multiplier: float = 2.0
):
    """
    Decorator for retrying synchronous operations on transient errors.

    Same as retry_on_transient_error but for synchronous functions.
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=multiplier, min=initial_wait, max=max_wait),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, "WARNING"),
        after=after_log(logger, "INFO"),
        reraise=True
    )
