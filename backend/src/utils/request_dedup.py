"""
Request deduplication utility to prevent duplicate LLM calls.

This module provides an in-memory cache for deduplicating identical requests
within a configurable time window (TTL). This is useful for:
- Preventing duplicate LLM calls when users send the same message multiple times
- Handling network retries without making duplicate API calls
- Caching responses for identical queries within a short time window
"""

import asyncio
import hashlib
import time
from typing import Optional, Any, Dict, Callable, Awaitable, TypeVar
from dataclasses import dataclass
from loguru import logger
import os

T = TypeVar("T")


@dataclass
class CachedResult:
    """Represents a cached result with expiration time."""

    result: Any
    expires_at: float


class RequestDeduplicator:
    """
    In-memory request deduplication with TTL.

    This class caches request results to prevent duplicate processing
    of identical requests within a time window.

    Example:
        deduplicator = RequestDeduplicator(ttl_seconds=30)

        # Check if request is cached, otherwise execute
        result = await deduplicator.get_or_execute(
            user_id="user123",
            notebook_id="notebook456",
            message="What is the meaning of life?",
            coro=llm_api.call(...)
        )
    """

    def __init__(self, ttl_seconds: int = 30):
        """
        Initialize the deduplicator.

        Args:
            ttl_seconds: Time-to-live for cached results in seconds.
                       Default is 30 seconds. Maximum allowed is 300 seconds.
        """
        self._cache: Dict[str, CachedResult] = {}
        self._ttl = min(ttl_seconds, 300)  # Cap at 5 minutes
        self._lock = asyncio.Lock()

        # Start cleanup task in background
        self._cleanup_task: Optional[asyncio.Task] = None

        logger.info(f"RequestDeduplicator initialized with TTL={self._ttl}s")

    def _generate_key(self, user_id: str, notebook_id: str, message: str) -> str:
        """
        Generate a unique cache key for a request.

        The key is a SHA256 hash of user_id, notebook_id, and message hash
        to ensure uniqueness while keeping the key deterministic.

        Args:
            user_id: The user's unique identifier
            notebook_id: The notebook's unique identifier
            message: The message content

        Returns:
            A 32-character hex string as the cache key
        """
        # Hash the message content first
        message_hash = hashlib.sha256(message.encode()).hexdigest()

        # Create composite key
        composite = f"{user_id}:{notebook_id}:{message_hash}"

        # Return a shorter hash for the key
        return hashlib.sha256(composite.encode()).hexdigest()[:32]

    async def get_or_execute(
        self, user_id: str, notebook_id: str, message: str, coro: Awaitable[T]
    ) -> T:
        """
        Get cached result or execute the coroutine and cache the result.

        This method checks if an identical request has been made within
        the TTL window. If found, it returns the cached result instead
        of executing the coroutine.

        Args:
            user_id: The user's unique identifier
            notebook_id: The notebook's unique identifier
            message: The message content
            coro: The coroutine to execute if not cached

        Returns:
            The result from cache or from executing the coroutine
        """
        key = self._generate_key(user_id, notebook_id, message)

        async with self._lock:
            # Check if we have a valid cached result
            if key in self._cache:
                cached = self._cache[key]
                current_time = time.time()

                if current_time < cached.expires_at:
                    # Cache hit - return cached result
                    logger.info(
                        f"Request deduplication: Cache HIT for key {key[:8]}... "
                        f"(user={user_id[:8]}..., notebook={notebook_id[:8]}...)"
                    )
                    return cached.result
                else:
                    # Cache expired - remove it
                    logger.debug(f"Cache expired for key {key[:8]}...")
                    del self._cache[key]

            # Cache miss - execute the coroutine
            logger.info(
                f"Request deduplication: Cache MISS for key {key[:8]}... "
                f"(user={user_id[:8]}..., notebook={notebook_id[:8]}...)"
            )

        # Execute outside the lock to allow concurrent execution of different keys
        result = await coro

        # Cache the result
        async with self._lock:
            self._cache[key] = CachedResult(
                result=result, expires_at=time.time() + self._ttl
            )

        return result

    async def get_or_execute_with_key(self, key: str, coro: Awaitable[T]) -> T:
        """
        Get cached result using a pre-generated key.

        This is useful when you want to generate the key yourself,
        for example for more complex deduplication logic.

        Args:
            key: Pre-generated cache key
            coro: The coroutine to execute if not cached

        Returns:
            The result from cache or from executing the coroutine
        """
        async with self._lock:
            if key in self._cache:
                cached = self._cache[key]
                current_time = time.time()

                if current_time < cached.expires_at:
                    logger.debug(f"Cache HIT for key {key[:8]}...")
                    return cached.result
                else:
                    del self._cache[key]

        result = await coro

        async with self._lock:
            self._cache[key] = CachedResult(
                result=result, expires_at=time.time() + self._ttl
            )

        return result

    def invalidate(self, user_id: str, notebook_id: str, message: str) -> bool:
        """
        Manually invalidate a cached result.

        Args:
            user_id: The user's unique identifier
            notebook_id: The notebook's unique identifier
            message: The message content

        Returns:
            True if a cached entry was invalidated, False otherwise
        """
        key = self._generate_key(user_id, notebook_id, message)

        if key in self._cache:
            del self._cache[key]
            logger.info(f"Invalidated cache for key {key[:8]}...")
            return True

        return False

    def clear(self) -> int:
        """
        Clear all cached results.

        Returns:
            Number of cached entries cleared
        """
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cleared {count} cached requests")
        return count

    def clear_expired(self) -> int:
        """
        Clear all expired cached results.

        Returns:
            Number of expired entries cleared
        """
        current_time = time.time()
        expired_keys = [
            k for k, v in self._cache.items() if current_time >= v.expires_at
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleared {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    @property
    def size(self) -> int:
        """Get the current number of cached entries."""
        return len(self._cache)

    @property
    def stats(self) -> Dict[str, Any]:
        """Get deduplicator statistics."""
        current_time = time.time()
        expired_count = sum(
            1 for v in self._cache.values() if current_time >= v.expires_at
        )

        return {
            "total_cached": len(self._cache),
            "expired_cached": expired_count,
            "active_cached": len(self._cache) - expired_count,
            "ttl_seconds": self._ttl,
        }

    async def start_cleanup_task(self, interval_seconds: int = 60):
        """
        Start a background task to periodically clean up expired entries.

        Args:
            interval_seconds: How often to run cleanup (default 60 seconds)
        """
        if self._cleanup_task is not None:
            return

        async def cleanup_loop():
            while True:
                await asyncio.sleep(interval_seconds)
                try:
                    self.clear_expired()
                except Exception as e:
                    logger.error(f"Error in cleanup task: {e}")

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info(f"Started cleanup task with interval={interval_seconds}s")

    async def stop_cleanup_task(self):
        """Stop the background cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Stopped cleanup task")


# Global deduplicator instance
# Configure TTL from environment variable (default 30 seconds)
_dedup_ttl = int(os.getenv("REQUEST_DEDUP_TTL_SECONDS", "30"))

# Global instance with configurable TTL
_deduplicator: Optional[RequestDeduplicator] = None


def get_deduplicator() -> RequestDeduplicator:
    """
    Get the global deduplicator instance.

    Returns:
        The global RequestDeduplicator instance
    """
    global _deduplicator

    if _deduplicator is None:
        _deduplicator = RequestDeduplicator(ttl_seconds=_dedup_ttl)
        logger.info(f"Created global deduplicator with TTL={_dedup_ttl}s")

    return _deduplicator


async def get_deduplicated_response(
    user_id: str, notebook_id: str, message: str, coro: Awaitable[T]
) -> T:
    """
    Convenience function to get a deduplicated response.

    This is a simple wrapper around the global deduplicator's get_or_execute method.

    Args:
        user_id: The user's unique identifier
        notebook_id: The notebook's unique identifier
        message: The message content
        coro: The coroutine to execute if not cached

    Returns:
        The result from cache or from executing the coroutine
    """
    deduplicator = get_deduplicator()
    return await deduplicator.get_or_execute(
        user_id=user_id, notebook_id=notebook_id, message=message, coro=coro
    )
