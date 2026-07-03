"""
Caching utilities for Granthiq.

Provides async-compatible caching with TTL support for:
- Query results
- Query embeddings
- Notebook document lists
- Filter building results
"""

import asyncio
import hashlib
import time
from typing import Any, Dict, Generic, List, Optional, TypeVar, Callable, Awaitable
from dataclasses import dataclass
from loguru import logger
from functools import wraps

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Cache entry with TTL support."""
    value: T
    expires_at: float
    access_count: int = 0
    last_accessed: float = 0.0


class AsyncTTLCache(Generic[T]):
    """
    Thread-safe async TTL cache with LRU eviction.
    
    Features:
    - TTL-based expiration
    - LRU eviction when max_size is reached
    - Async-safe operations
    - Background cleanup task
    """
    
    def __init__(
        self,
        name: str,
        default_ttl: float = 300.0,  # 5 minutes default
        max_size: int = 1000,
        cleanup_interval: float = 60.0,  # Cleanup every minute
    ):
        self.name = name
        self.default_ttl = default_ttl
        self.max_size = max_size
        self.cleanup_interval = cleanup_interval
        self._cache: Dict[str, CacheEntry[T]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._hits = 0
        self._misses = 0
        
    async def start(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.debug(f"Started cleanup task for cache '{self.name}'")
    
    async def stop(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.debug(f"Stopped cleanup task for cache '{self.name}'")
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean expired entries."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Cache cleanup error in '{self.name}': {e}")
    
    async def _cleanup_expired(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        now = time.time()
        removed = 0
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.expires_at < now
            ]
            for key in expired_keys:
                del self._cache[key]
                removed += 1
        if removed > 0:
            logger.debug(f"Cleaned up {removed} expired entries from cache '{self.name}'")
        return removed
    
    async def _evict_lru(self) -> None:
        """Evict least recently used entry when cache is full."""
        if len(self._cache) < self.max_size:
            return
        
        # Find LRU entry
        lru_key = min(
            self._cache.keys(),
            key=lambda k: (self._cache[k].access_count, self._cache[k].last_accessed)
        )
        del self._cache[lru_key]
        logger.debug(f"Evicted LRU entry '{lru_key}' from cache '{self.name}'")
    
    async def get(self, key: str) -> Optional[T]:
        """Get value from cache if not expired."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            
            if entry.expires_at < time.time():
                # Expired
                del self._cache[key]
                self._misses += 1
                return None
            
            # Update access stats
            entry.access_count += 1
            entry.last_accessed = time.time()
            self._hits += 1
            return entry.value
    
    async def set(
        self,
        key: str,
        value: T,
        ttl: Optional[float] = None
    ) -> None:
        """Set value in cache with optional custom TTL."""
        ttl = ttl or self.default_ttl
        expires_at = time.time() + ttl
        
        async with self._lock:
            # Evict if necessary
            if key not in self._cache and len(self._cache) >= self.max_size:
                await self._evict_lru()
            
            self._cache[key] = CacheEntry(
                value=value,
                expires_at=expires_at,
                access_count=0,
                last_accessed=time.time()
            )
    
    async def delete(self, key: str) -> bool:
        """Delete entry from cache. Returns True if key existed."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    async def clear(self) -> None:
        """Clear all entries from cache."""
        async with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "name": self.name,
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "default_ttl": self.default_ttl,
        }


# Global cache instances
_query_result_cache: Optional[AsyncTTLCache[Any]] = None
_query_embedding_cache: Optional[AsyncTTLCache[List[float]]] = None
_notebook_docs_cache: Optional[AsyncTTLCache[List[Any]]] = None
_filter_cache: Optional[AsyncTTLCache[Any]] = None


def get_query_result_cache() -> AsyncTTLCache[Any]:
    """Get global query result cache."""
    global _query_result_cache
    if _query_result_cache is None:
        _query_result_cache = AsyncTTLCache(
            name="query_results",
            default_ttl=60.0,  # 1 minute for query results
            max_size=500,
        )
    return _query_result_cache


def get_query_embedding_cache() -> AsyncTTLCache[List[float]]:
    """Get global query embedding cache."""
    global _query_embedding_cache
    if _query_embedding_cache is None:
        _query_embedding_cache = AsyncTTLCache(
            name="query_embeddings",
            default_ttl=300.0,  # 5 minutes for embeddings
            max_size=1000,
        )
    return _query_embedding_cache


def get_notebook_docs_cache() -> AsyncTTLCache[List[Any]]:
    """Get global notebook documents cache."""
    global _notebook_docs_cache
    if _notebook_docs_cache is None:
        _notebook_docs_cache = AsyncTTLCache(
            name="notebook_docs",
            default_ttl=30.0,  # 30 seconds for document lists
            max_size=200,
        )
    return _notebook_docs_cache


def get_filter_cache() -> AsyncTTLCache[Any]:
    """Get global filter cache."""
    global _filter_cache
    if _filter_cache is None:
        _filter_cache = AsyncTTLCache(
            name="filters",
            default_ttl=10.0,  # 10 seconds for filters
            max_size=300,
        )
    return _filter_cache


def generate_cache_key(*args: Any, **kwargs: Any) -> str:
    """Generate a cache key from arguments."""
    key_parts = []
    
    # Add positional args
    for arg in args:
        if isinstance(arg, (str, int, float, bool)):
            key_parts.append(str(arg))
        elif isinstance(arg, bytes):
            key_parts.append(hashlib.md5(arg).hexdigest()[:16])
        else:
            key_parts.append(str(hash(arg)))
    
    # Add keyword args (sorted for consistency)
    for key in sorted(kwargs.keys()):
        value = kwargs[key]
        if isinstance(value, (str, int, float, bool)):
            key_parts.append(f"{key}={value}")
        elif isinstance(value, bytes):
            key_parts.append(f"{key}={hashlib.md5(value).hexdigest()[:16]}")
        else:
            key_parts.append(f"{key}={hash(value)}")
    
    combined = "|".join(key_parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


def cached(
    cache: Optional[AsyncTTLCache[T]] = None,
    ttl: Optional[float] = None,
    key_func: Optional[Callable[..., str]] = None
):
    """
    Decorator for caching async function results.
    
    Args:
        cache: Cache instance to use. If None, uses default query result cache.
        ttl: Optional custom TTL for this function.
        key_func: Optional custom key generation function.
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            cache_instance = cache or get_query_result_cache()
            
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = generate_cache_key(func.__name__, *args, **kwargs)
            
            # Try to get from cache
            cached_value = await cache_instance.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_value
            
            # Compute and cache
            result = await func(*args, **kwargs)
            await cache_instance.set(cache_key, result, ttl=ttl)
            return result
        
        return wrapper
    return decorator


async def invalidate_notebook_cache(notebook_id: str) -> None:
    """Invalidate all caches related to a notebook."""
    cache = get_notebook_docs_cache()
    # Clear all entries that might contain this notebook's data
    # For simplicity, we clear the entire cache when a notebook changes
    await cache.clear()
    logger.debug(f"Invalidated notebook cache for {notebook_id}")


async def start_all_caches() -> None:
    """Start all global cache cleanup tasks."""
    caches = [
        get_query_result_cache(),
        get_query_embedding_cache(),
        get_notebook_docs_cache(),
        get_filter_cache(),
    ]
    
    for cache in caches:
        await cache.start()
    
    logger.info("All caches started")


async def stop_all_caches() -> None:
    """Stop all global cache cleanup tasks."""
    caches = [
        get_query_result_cache(),
        get_query_embedding_cache(),
        get_notebook_docs_cache(),
        get_filter_cache(),
    ]
    
    for cache in caches:
        await cache.stop()
    
    logger.info("All caches stopped")


def get_all_cache_stats() -> List[Dict[str, Any]]:
    """Get statistics for all caches."""
    return [
        get_query_result_cache().get_stats(),
        get_query_embedding_cache().get_stats(),
        get_notebook_docs_cache().get_stats(),
        get_filter_cache().get_stats(),
    ]

