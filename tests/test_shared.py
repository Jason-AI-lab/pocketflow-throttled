"""
Tests for Shared Rate Limiters
==============================

Tests for LimiterRegistry and shared rate limiting functionality.
"""

import asyncio
import pytest

from pocketflow_throttled import LimiterRegistry, RateLimiter


class TestLimiterRegistry:
    """Tests for LimiterRegistry."""
    
    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset the registry before and after each test."""
        LimiterRegistry.reset()
        yield
        LimiterRegistry.reset()
    
    def test_register_limiter(self):
        """Test registering a limiter."""
        limiter = LimiterRegistry.register(
            "test_api",
            max_concurrent=5,
            max_per_window=60
        )
        
        assert isinstance(limiter, RateLimiter)
        assert LimiterRegistry.exists("test_api")
    
    def test_get_limiter(self):
        """Test getting a registered limiter."""
        LimiterRegistry.register("my_limiter", max_concurrent=10)
        
        limiter = LimiterRegistry.get("my_limiter")
        assert limiter._max_concurrent == 10
    
    def test_get_nonexistent_raises(self):
        """Test that getting a non-existent limiter raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            LimiterRegistry.get("nonexistent")
        
        assert "nonexistent" in str(exc_info.value)
    
    def test_register_duplicate_raises(self):
        """Test that registering a duplicate raises ValueError."""
        LimiterRegistry.register("api", max_concurrent=5)
        
        with pytest.raises(ValueError) as exc_info:
            LimiterRegistry.register("api", max_concurrent=10)
        
        assert "already exists" in str(exc_info.value)
    
    def test_register_with_replace(self):
        """Test replacing an existing limiter."""
        LimiterRegistry.register("api", max_concurrent=5)
        LimiterRegistry.register("api", max_concurrent=10, replace=True)
        
        limiter = LimiterRegistry.get("api")
        assert limiter._max_concurrent == 10
    
    def test_get_or_create_creates(self):
        """Test get_or_create creates new limiter."""
        limiter = LimiterRegistry.get_or_create(
            "new_api",
            max_concurrent=15
        )
        
        assert limiter._max_concurrent == 15
        assert LimiterRegistry.exists("new_api")
    
    def test_get_or_create_gets_existing(self):
        """Test get_or_create returns existing limiter."""
        LimiterRegistry.register("existing", max_concurrent=5)
        
        # Try to create with different config
        limiter = LimiterRegistry.get_or_create(
            "existing",
            max_concurrent=100  # This should be ignored
        )
        
        # Should return the original limiter
        assert limiter._max_concurrent == 5
    
    def test_remove_limiter(self):
        """Test removing a limiter."""
        LimiterRegistry.register("to_remove", max_concurrent=5)
        
        assert LimiterRegistry.exists("to_remove")
        assert LimiterRegistry.remove("to_remove") is True
        assert not LimiterRegistry.exists("to_remove")
    
    def test_remove_nonexistent(self):
        """Test removing a non-existent limiter returns False."""
        assert LimiterRegistry.remove("nonexistent") is False
    
    def test_reset_single(self):
        """Test resetting a single limiter."""
        LimiterRegistry.register("a", max_concurrent=5)
        LimiterRegistry.register("b", max_concurrent=10)
        
        LimiterRegistry.reset("a")
        
        assert not LimiterRegistry.exists("a")
        assert LimiterRegistry.exists("b")
    
    def test_reset_all(self):
        """Test resetting all limiters."""
        LimiterRegistry.register("a", max_concurrent=5)
        LimiterRegistry.register("b", max_concurrent=10)
        LimiterRegistry.register("c", max_concurrent=15)
        
        LimiterRegistry.reset()
        
        assert not LimiterRegistry.exists("a")
        assert not LimiterRegistry.exists("b")
        assert not LimiterRegistry.exists("c")
    
    def test_list_names(self):
        """Test listing limiter names."""
        LimiterRegistry.register("api1", max_concurrent=5)
        LimiterRegistry.register("api2", max_concurrent=10)
        
        names = LimiterRegistry.list_names()
        
        assert "api1" in names
        assert "api2" in names
        assert len(names) == 2
    
    def test_list_all(self):
        """Test listing all limiters with config."""
        LimiterRegistry.register("api1", max_concurrent=5, max_per_window=60)
        LimiterRegistry.register("api2", max_concurrent=10, max_per_window=None)
        
        all_limiters = LimiterRegistry.list_all()
        
        assert all_limiters["api1"]["max_concurrent"] == 5
        assert all_limiters["api1"]["max_per_window"] == 60
        assert all_limiters["api2"]["max_concurrent"] == 10
        assert all_limiters["api2"]["max_per_window"] is None
    
    def test_stats(self):
        """Test getting limiter stats."""
        LimiterRegistry.register(
            "api",
            max_concurrent=5,
            max_per_window=100,
            window_seconds=30.0
        )
        
        stats = LimiterRegistry.stats("api")
        
        assert stats["max_concurrent"] == 5
        assert stats["max_per_window"] == 100
        assert stats["window_seconds"] == 30.0
        assert "current_window_count" in stats
    
    @pytest.mark.asyncio
    async def test_shared_limiter_usage(self):
        """Test using shared limiter across multiple tasks."""
        LimiterRegistry.register("shared", max_concurrent=2)
        
        concurrent_count = 0
        max_seen = 0
        lock = asyncio.Lock()
        
        async def task(task_id: int):
            nonlocal concurrent_count, max_seen
            
            async with LimiterRegistry.get("shared"):
                async with lock:
                    concurrent_count += 1
                    max_seen = max(max_seen, concurrent_count)
                
                await asyncio.sleep(0.05)
                
                async with lock:
                    concurrent_count -= 1
            
            return task_id
        
        # Run 10 tasks concurrently
        results = await asyncio.gather(*[task(i) for i in range(10)])
        
        assert len(results) == 10
        assert max_seen <= 2  # Should never exceed max_concurrent
    
    @pytest.mark.asyncio
    async def test_different_limiters_independent(self):
        """Test that different limiters are independent."""
        LimiterRegistry.register("api_a", max_concurrent=2)
        LimiterRegistry.register("api_b", max_concurrent=3)
        
        a_count = 0
        b_count = 0
        a_max = 0
        b_max = 0
        lock = asyncio.Lock()
        
        async def task_a():
            nonlocal a_count, a_max
            async with LimiterRegistry.get("api_a"):
                async with lock:
                    a_count += 1
                    a_max = max(a_max, a_count)
                await asyncio.sleep(0.03)
                async with lock:
                    a_count -= 1
        
        async def task_b():
            nonlocal b_count, b_max
            async with LimiterRegistry.get("api_b"):
                async with lock:
                    b_count += 1
                    b_max = max(b_max, b_count)
                await asyncio.sleep(0.03)
                async with lock:
                    b_count -= 1
        
        # Run tasks for both APIs
        await asyncio.gather(
            *[task_a() for _ in range(5)],
            *[task_b() for _ in range(5)]
        )
        
        assert a_max <= 2
        assert b_max <= 3


class TestRateLimitHitException:
    """Tests for RateLimitHit exception."""
    
    def test_basic_exception(self):
        """Test basic RateLimitHit exception."""
        from pocketflow_throttled import RateLimitHit
        
        exc = RateLimitHit("Test rate limit")
        assert str(exc) == "Test rate limit"
        assert exc.retry_after is None
        assert exc.source is None
    
    def test_with_retry_after(self):
        """Test RateLimitHit with retry_after."""
        from pocketflow_throttled import RateLimitHit
        
        exc = RateLimitHit("Rate limit", retry_after=30.0)
        assert exc.retry_after == 30.0
    
    def test_with_source(self):
        """Test RateLimitHit with source."""
        from pocketflow_throttled import RateLimitHit
        
        exc = RateLimitHit("Rate limit", source="openai")
        assert exc.source == "openai"
    
    def test_repr(self):
        """Test RateLimitHit repr."""
        from pocketflow_throttled import RateLimitHit
        
        exc = RateLimitHit("Test", retry_after=10.0, source="api")
        repr_str = repr(exc)
        
        assert "RateLimitHit" in repr_str
        assert "Test" in repr_str
        assert "retry_after=10.0" in repr_str
        assert "source='api'" in repr_str
