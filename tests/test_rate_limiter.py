"""
Tests for the RateLimiter class.
"""

import asyncio
import time
import pytest

from pocketflow_throttled import RateLimiter


class TestRateLimiterInit:
    """Tests for RateLimiter initialization."""
    
    def test_default_values(self):
        """Test default initialization values."""
        limiter = RateLimiter()
        assert limiter.max_concurrent == 5
        assert limiter.max_per_window is None
        assert limiter.window_seconds == 60.0
    
    def test_custom_values(self):
        """Test custom initialization values."""
        limiter = RateLimiter(
            max_concurrent=10,
            max_per_window=100,
            window_seconds=30.0
        )
        assert limiter.max_concurrent == 10
        assert limiter.max_per_window == 100
        assert limiter.window_seconds == 30.0
    
    def test_invalid_max_concurrent(self):
        """Test that max_concurrent must be at least 1."""
        with pytest.raises(ValueError, match="max_concurrent must be at least 1"):
            RateLimiter(max_concurrent=0)
    
    def test_invalid_max_per_window(self):
        """Test that max_per_window must be at least 1 or None."""
        with pytest.raises(ValueError, match="max_per_window must be at least 1"):
            RateLimiter(max_per_window=0)
    
    def test_invalid_window_seconds(self):
        """Test that window_seconds must be positive."""
        with pytest.raises(ValueError, match="window_seconds must be positive"):
            RateLimiter(window_seconds=0)
    
    def test_repr(self):
        """Test string representation."""
        limiter = RateLimiter(max_concurrent=3, max_per_window=60, window_seconds=60)
        repr_str = repr(limiter)
        assert "max_concurrent=3" in repr_str
        assert "max_per_window=60" in repr_str
        assert "window_seconds=60" in repr_str


class TestConcurrencyLimit:
    """Tests for concurrency limiting (semaphore behavior)."""
    
    @pytest.mark.asyncio
    async def test_concurrency_is_limited(self):
        """Verify that max_concurrent tasks run simultaneously."""
        limiter = RateLimiter(max_concurrent=3)
        active = 0
        max_active = 0
        
        async def task():
            nonlocal active, max_active
            async with limiter:
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.05)
                active -= 1
        
        await asyncio.gather(*[task() for _ in range(10)])
        
        assert max_active == 3, f"Expected max 3 concurrent, got {max_active}"
    
    @pytest.mark.asyncio
    async def test_concurrency_one(self):
        """Test single concurrency (sequential execution)."""
        limiter = RateLimiter(max_concurrent=1)
        order = []
        
        async def task(n):
            async with limiter:
                order.append(f"start_{n}")
                await asyncio.sleep(0.01)
                order.append(f"end_{n}")
        
        await asyncio.gather(*[task(i) for i in range(3)])
        
        # With concurrency=1, tasks should not interleave
        assert order == [
            "start_0", "end_0",
            "start_1", "end_1", 
            "start_2", "end_2"
        ]
    
    @pytest.mark.asyncio
    async def test_high_concurrency(self):
        """Test that high concurrency allows parallel execution."""
        limiter = RateLimiter(max_concurrent=100)
        active = 0
        max_active = 0
        
        async def task():
            nonlocal active, max_active
            async with limiter:
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.1)
                active -= 1
        
        await asyncio.gather(*[task() for _ in range(50)])
        
        # All 50 should run concurrently
        assert max_active == 50


class TestThroughputLimit:
    """Tests for throughput limiting (sliding window behavior)."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_is_enforced(self):
        """Verify that max_per_window limits throughput."""
        # Allow 5 requests in 1 second
        limiter = RateLimiter(
            max_concurrent=100,  # High concurrency
            max_per_window=5,
            window_seconds=1.0
        )
        
        timestamps = []
        
        async def task():
            async with limiter:
                timestamps.append(time.monotonic())
        
        start = time.monotonic()
        await asyncio.gather(*[task() for _ in range(10)])
        elapsed = time.monotonic() - start
        
        # First 5 should be immediate, next 5 after ~1 second
        assert len(timestamps) == 10
        
        # Should take at least 1 second for 10 requests at 5/sec
        assert elapsed >= 0.9, f"Completed too fast: {elapsed}s"
    
    @pytest.mark.asyncio
    async def test_no_rate_limit(self):
        """Test that None max_per_window means no throughput limit."""
        limiter = RateLimiter(
            max_concurrent=100,
            max_per_window=None
        )
        
        start = time.monotonic()
        
        async def task():
            async with limiter:
                pass
        
        await asyncio.gather(*[task() for _ in range(50)])
        elapsed = time.monotonic() - start
        
        # Should complete very quickly with no rate limit
        assert elapsed < 0.5
    
    @pytest.mark.asyncio
    async def test_window_count_property(self):
        """Test the current_window_count property."""
        limiter = RateLimiter(
            max_concurrent=10,
            max_per_window=100,
            window_seconds=1.0
        )
        
        assert limiter.current_window_count == 0
        
        async with limiter:
            pass
        
        assert limiter.current_window_count == 1
        
        for _ in range(4):
            async with limiter:
                pass
        
        assert limiter.current_window_count == 5


class TestContextManager:
    """Tests for async context manager behavior."""
    
    @pytest.mark.asyncio
    async def test_context_manager_acquire_release(self):
        """Test that context manager properly acquires and releases."""
        limiter = RateLimiter(max_concurrent=1)
        
        acquired = False
        
        async def task1():
            nonlocal acquired
            async with limiter:
                acquired = True
                await asyncio.sleep(0.1)
        
        async def task2():
            # Wait a bit to ensure task1 starts first
            await asyncio.sleep(0.01)
            # This should block until task1 releases
            start = time.monotonic()
            async with limiter:
                elapsed = time.monotonic() - start
            return elapsed
        
        task1_coro = task1()
        task2_coro = task2()
        
        _, elapsed = await asyncio.gather(task1_coro, task2_coro)
        
        assert acquired
        assert elapsed >= 0.08  # Should have waited for task1
    
    @pytest.mark.asyncio
    async def test_context_manager_releases_on_exception(self):
        """Test that semaphore is released even if exception occurs."""
        limiter = RateLimiter(max_concurrent=1)
        
        async def failing_task():
            async with limiter:
                raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await failing_task()
        
        # Semaphore should be released, so this should not block
        start = time.monotonic()
        async with limiter:
            elapsed = time.monotonic() - start
        
        assert elapsed < 0.1


class TestReset:
    """Tests for the reset functionality."""
    
    @pytest.mark.asyncio
    async def test_reset_clears_timestamps(self):
        """Test that reset() clears the sliding window."""
        limiter = RateLimiter(
            max_concurrent=10,
            max_per_window=5,
            window_seconds=60.0
        )
        
        # Fill up the window
        for _ in range(5):
            async with limiter:
                pass
        
        assert limiter.current_window_count == 5
        
        limiter.reset()
        
        assert limiter.current_window_count == 0


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""
    
    @pytest.mark.asyncio
    async def test_zero_latency_tasks(self):
        """Test with tasks that complete instantly."""
        limiter = RateLimiter(max_concurrent=5, max_per_window=100)
        
        results = []
        
        async def task(n):
            async with limiter:
                results.append(n)
        
        await asyncio.gather(*[task(i) for i in range(20)])
        
        assert len(results) == 20
        assert set(results) == set(range(20))
    
    @pytest.mark.asyncio
    async def test_mixed_task_durations(self):
        """Test with tasks of varying durations."""
        limiter = RateLimiter(max_concurrent=3)
        
        completed = []
        
        async def task(n, duration):
            async with limiter:
                await asyncio.sleep(duration)
                completed.append(n)
        
        tasks = [
            task(0, 0.1),
            task(1, 0.05),
            task(2, 0.15),
            task(3, 0.02),
            task(4, 0.08),
        ]
        
        await asyncio.gather(*tasks)
        
        assert len(completed) == 5
        assert set(completed) == {0, 1, 2, 3, 4}
