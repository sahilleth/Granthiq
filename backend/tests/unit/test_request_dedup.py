"""
Tests for request deduplication functionality.
"""

import pytest
import asyncio
import time
from src.utils.request_dedup import (
    RequestDeduplicator,
    get_deduplicator,
    get_deduplicated_response,
)


class TestRequestDeduplicator:
    """Tests for RequestDeduplicator class."""

    @pytest.fixture
    def dedup(self):
        """Create a fresh deduplicator for each test."""
        return RequestDeduplicator(ttl_seconds=2)

    @pytest.mark.asyncio
    async def test_cache_miss(self, dedup):
        """Test that first call executes the coroutine."""
        call_count = 0

        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return "result"

        result = await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb1",
            message="test message",
            coro=expensive_operation(),
        )

        assert result == "result"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_cache_hit(self, dedup):
        """Test that duplicate calls return cached result."""
        call_count = 0

        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return "result"

        # First call
        result1 = await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb1",
            message="test message",
            coro=expensive_operation(),
        )

        # Second call with same parameters
        result2 = await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb1",
            message="test message",
            coro=expensive_operation(),
        )

        assert result1 == result2 == "result"
        assert call_count == 1  # Only called once

    @pytest.mark.asyncio
    async def test_different_users_no_cache(self, dedup):
        """Test that different users don't share cache."""
        call_count = 0

        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            return "result"

        # First user
        await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb1",
            message="test message",
            coro=expensive_operation(),
        )

        # Second user with same message
        await dedup.get_or_execute(
            user_id="user2",
            notebook_id="nb1",
            message="test message",
            coro=expensive_operation(),
        )

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_different_notebooks_no_cache(self, dedup):
        """Test that different notebooks don't share cache."""
        call_count = 0

        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            return "result"

        await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb1",
            message="test message",
            coro=expensive_operation(),
        )

        await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb2",
            message="test message",
            coro=expensive_operation(),
        )

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_different_messages_no_cache(self, dedup):
        """Test that different messages don't share cache."""
        call_count = 0

        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            return "result"

        await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb1",
            message="message one",
            coro=expensive_operation(),
        )

        await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb1",
            message="message two",
            coro=expensive_operation(),
        )

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, dedup):
        """Test that cache expires after TTL."""
        call_count = 0

        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            return "result"

        # First call
        await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb1",
            message="test",
            coro=expensive_operation(),
        )

        assert call_count == 1

        # Wait for TTL to expire
        await asyncio.sleep(2.5)

        # Third call should execute again
        await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb1",
            message="test",
            coro=expensive_operation(),
        )

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_invalidate(self, dedup):
        """Test manual cache invalidation."""
        call_count = 0

        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            return "result"

        # First call
        await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb1",
            message="test",
            coro=expensive_operation(),
        )

        assert call_count == 1

        # Invalidate
        dedup.invalidate("user1", "nb1", "test")

        # Second call should execute again
        await dedup.get_or_execute(
            user_id="user1",
            notebook_id="nb1",
            message="test",
            coro=expensive_operation(),
        )

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_clear(self, dedup):
        """Test clearing all cached entries."""
        call_count = 0

        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            return "result"

        # Add multiple entries
        await dedup.get_or_execute("u1", "n1", "m1", expensive_operation())
        await dedup.get_or_execute("u1", "n1", "m2", expensive_operation())

        assert call_count == 2
        assert dedup.size == 2

        # Clear
        dedup.clear()

        assert dedup.size == 0

        # Next calls should execute
        await dedup.get_or_execute("u1", "n1", "m1", expensive_operation())
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_clear_expired(self, dedup):
        """Test clearing expired entries."""
        call_count = 0

        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            return "result"

        # Add entry
        await dedup.get_or_execute("u1", "n1", "m1", expensive_operation())
        assert dedup.size == 1

        # Wait for expiration
        await asyncio.sleep(2.5)

        # Clear expired
        cleared = dedup.clear_expired()

        assert cleared == 1
        assert dedup.size == 0

    def test_stats(self, dedup):
        """Test deduplicator statistics."""
        stats = dedup.stats

        assert "total_cached" in stats
        assert "ttl_seconds" in stats
        assert stats["ttl_seconds"] == 2


class TestGlobalDeduplicator:
    """Tests for global deduplicator instance."""

    def test_get_deduplicator_singleton(self):
        """Test that get_deduplicator returns singleton."""
        d1 = get_deduplicator()
        d2 = get_deduplicator()

        assert d1 is d2

    @pytest.mark.asyncio
    async def test_get_deduplicated_response_function(self):
        """Test convenience function."""
        call_count = 0

        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            return "result"

        # First call
        result1 = await get_deduplicated_response(
            user_id="user1",
            notebook_id="nb1",
            message="test",
            coro=expensive_operation(),
        )

        # Second call
        result2 = await get_deduplicated_response(
            user_id="user1",
            notebook_id="nb1",
            message="test",
            coro=expensive_operation(),
        )

        assert result1 == result2 == "result"
        assert call_count == 1


class TestKeyGeneration:
    """Tests for cache key generation."""

    def test_key_generation_deterministic(self):
        """Test that key generation is deterministic."""
        dedup = RequestDeduplicator(ttl_seconds=30)

        key1 = dedup._generate_key("user1", "nb1", "message")
        key2 = dedup._generate_key("user1", "nb1", "message")

        assert key1 == key2

    def test_key_generation_different_inputs(self):
        """Test that different inputs produce different keys."""
        dedup = RequestDeduplicator(ttl_seconds=30)

        key1 = dedup._generate_key("user1", "nb1", "message1")
        key2 = dedup._generate_key("user1", "nb1", "message2")

        assert key1 != key2

    def test_key_format(self):
        """Test that key is proper format."""
        dedup = RequestDeduplicator(ttl_seconds=30)

        key = dedup._generate_key("user1", "nb1", "message")

        assert isinstance(key, str)
        assert len(key) == 32  # SHA256 hexdigest truncated to 32 chars
