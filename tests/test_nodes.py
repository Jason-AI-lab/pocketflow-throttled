"""
Tests for ThrottledParallelBatchNode and AdaptiveThrottledNode.
"""

import asyncio
import time
import pytest

from pocketflow import AsyncFlow
from pocketflow_throttled import (
    ThrottledParallelBatchNode,
    AdaptiveThrottledNode,
    RateLimiter,
)


# =============================================================================
# Test Fixtures and Helper Classes
# =============================================================================

class SimpleThrottledNode(ThrottledParallelBatchNode):
    """Simple test node that processes items."""
    max_concurrent = 3
    max_per_minute = None
    
    async def prep_async(self, shared):
        return shared.get("items", [])
    
    async def exec_async(self, item):
        await asyncio.sleep(0.01)  # Simulate work
        return item * 2
    
    async def post_async(self, shared, prep_res, exec_res_list):
        shared["results"] = exec_res_list
        return "default"


class TrackingThrottledNode(ThrottledParallelBatchNode):
    """Node that tracks execution timing for verification."""
    max_concurrent = 2
    max_per_minute = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.execution_times = []
        self.active_count = 0
        self.max_active = 0
    
    async def prep_async(self, shared):
        return shared.get("items", [])
    
    async def exec_async(self, item):
        self.active_count += 1
        self.max_active = max(self.max_active, self.active_count)
        self.execution_times.append(time.monotonic())
        await asyncio.sleep(0.05)
        self.active_count -= 1
        return item
    
    async def post_async(self, shared, prep_res, exec_res_list):
        shared["results"] = exec_res_list
        return "default"


class RateLimitSimulatorNode(ThrottledParallelBatchNode):
    """Node that simulates rate limit errors."""
    max_concurrent = 5
    
    def __init__(self, fail_until=3, **kwargs):
        super().__init__(**kwargs)
        self.call_count = 0
        self.fail_until = fail_until
    
    async def prep_async(self, shared):
        return shared.get("items", [])
    
    async def exec_async(self, item):
        self.call_count += 1
        if self.call_count <= self.fail_until:
            raise Exception("429 Too Many Requests")
        return item
    
    async def post_async(self, shared, prep_res, exec_res_list):
        shared["results"] = exec_res_list
        return "default"


# =============================================================================
# ThrottledParallelBatchNode Tests
# =============================================================================

class TestThrottledParallelBatchNodeBasic:
    """Basic functionality tests."""
    
    @pytest.mark.asyncio
    async def test_processes_all_items(self):
        """Test that all items are processed."""
        node = SimpleThrottledNode()
        shared = {"items": [1, 2, 3, 4, 5]}
        
        await node._run_async(shared)
        
        assert shared["results"] == [2, 4, 6, 8, 10]
    
    @pytest.mark.asyncio
    async def test_empty_items(self):
        """Test handling of empty item list."""
        node = SimpleThrottledNode()
        shared = {"items": []}
        
        await node._run_async(shared)
        
        assert shared["results"] == []
    
    @pytest.mark.asyncio
    async def test_single_item(self):
        """Test processing a single item."""
        node = SimpleThrottledNode()
        shared = {"items": [42]}
        
        await node._run_async(shared)
        
        assert shared["results"] == [84]


class TestThrottledParallelBatchNodeConcurrency:
    """Tests for concurrency limiting behavior."""
    
    @pytest.mark.asyncio
    async def test_respects_max_concurrent(self):
        """Verify max_concurrent limit is enforced."""
        node = TrackingThrottledNode()
        shared = {"items": list(range(10))}
        
        await node._run_async(shared)
        
        assert node.max_active == 2, f"Expected max 2 concurrent, got {node.max_active}"
    
    @pytest.mark.asyncio
    async def test_custom_max_concurrent(self):
        """Test setting max_concurrent via constructor."""
        node = TrackingThrottledNode(max_concurrent=5)
        node.max_concurrent = 5  # Override class default
        shared = {"items": list(range(20))}
        
        await node._run_async(shared)
        
        # Should allow up to 5 concurrent
        assert node.max_active <= 5


class TestThrottledParallelBatchNodeConfiguration:
    """Tests for configuration options."""
    
    def test_class_attribute_defaults(self):
        """Test that class attributes provide defaults."""
        class CustomNode(ThrottledParallelBatchNode):
            max_concurrent = 10
            max_per_minute = 120
        
        node = CustomNode()
        assert node.max_concurrent == 10
        assert node.max_per_minute == 120
    
    def test_constructor_kwargs_override(self):
        """Test that constructor kwargs override class defaults."""
        node = SimpleThrottledNode(max_concurrent=20, max_per_minute=200)
        
        assert node.max_concurrent == 20
        assert node.max_per_minute == 200
    
    def test_limiter_lazy_init(self):
        """Test that limiter is created on first access."""
        node = SimpleThrottledNode()
        
        # Before access, _limiter should be None
        assert node._limiter is None
        
        # Access limiter property
        limiter = node.limiter
        
        assert limiter is not None
        assert isinstance(limiter, RateLimiter)
        assert limiter.max_concurrent == node.max_concurrent
    
    def test_reset_limiter(self):
        """Test that reset_limiter clears the limiter."""
        node = SimpleThrottledNode()
        
        # Force limiter creation
        _ = node.limiter
        assert node._limiter is not None
        
        # Reset
        node.reset_limiter()
        assert node._limiter is None


class TestThrottledParallelBatchNodeRateLimitDetection:
    """Tests for rate limit error detection."""
    
    def test_detects_429_error(self):
        """Test detection of HTTP 429 errors."""
        exc = Exception("HTTP Error 429: Too Many Requests")
        assert ThrottledParallelBatchNode.is_rate_limit_error(exc)
    
    def test_detects_rate_limit_text(self):
        """Test detection of 'rate limit' in error message."""
        exc = Exception("Rate limit exceeded. Please try again later.")
        assert ThrottledParallelBatchNode.is_rate_limit_error(exc)
    
    def test_detects_quota_exceeded(self):
        """Test detection of quota exceeded errors."""
        exc = Exception("API quota exceeded for this billing period")
        assert ThrottledParallelBatchNode.is_rate_limit_error(exc)
    
    def test_ignores_other_errors(self):
        """Test that non-rate-limit errors are not detected."""
        exc = Exception("Connection timeout")
        assert not ThrottledParallelBatchNode.is_rate_limit_error(exc)
        
        exc = Exception("Invalid API key")
        assert not ThrottledParallelBatchNode.is_rate_limit_error(exc)


class TestThrottledParallelBatchNodeWithFlow:
    """Tests for integration with AsyncFlow."""
    
    @pytest.mark.asyncio
    async def test_works_with_async_flow(self):
        """Test that node works correctly within AsyncFlow."""
        node = SimpleThrottledNode()
        flow = AsyncFlow(start=node)
        
        shared = {"items": [1, 2, 3]}
        await flow.run_async(shared)
        
        assert shared["results"] == [2, 4, 6]


# =============================================================================
# AdaptiveThrottledNode Tests
# =============================================================================

class SimpleAdaptiveNode(AdaptiveThrottledNode):
    """Simple adaptive node for testing."""
    initial_concurrent = 5
    min_concurrent = 1
    max_concurrent = 20
    backoff_factor = 0.5
    recovery_threshold = 3  # Lower threshold for faster tests
    recovery_factor = 2.0
    
    async def prep_async(self, shared):
        return shared.get("items", [])
    
    async def exec_async(self, item):
        await asyncio.sleep(0.01)
        return item * 2
    
    async def post_async(self, shared, prep_res, exec_res_list):
        shared["results"] = exec_res_list
        return "default"


class TestAdaptiveThrottledNodeBasic:
    """Basic adaptive throttling tests."""
    
    @pytest.mark.asyncio
    async def test_starts_at_initial_concurrent(self):
        """Test that node starts at initial_concurrent level."""
        node = SimpleAdaptiveNode()
        
        assert node.current_concurrent == 5
    
    @pytest.mark.asyncio
    async def test_processes_items_successfully(self):
        """Test that adaptive node processes items correctly."""
        node = SimpleAdaptiveNode()
        shared = {"items": [1, 2, 3]}
        
        await node._run_async(shared)
        
        assert shared["results"] == [2, 4, 6]
    
    def test_stats_property(self):
        """Test the stats property."""
        node = SimpleAdaptiveNode()
        stats = node.stats
        
        assert "current_concurrent" in stats
        assert "total_successes" in stats
        assert "total_rate_limits" in stats
        assert "consecutive_successes" in stats
        
        assert stats["current_concurrent"] == 5
        assert stats["total_successes"] == 0
        assert stats["total_rate_limits"] == 0


class TestAdaptiveThrottledNodeBackoff:
    """Tests for backoff behavior on rate limits."""
    
    @pytest.mark.asyncio
    async def test_backs_off_on_rate_limit(self):
        """Test that concurrency decreases on rate limit error."""
        node = SimpleAdaptiveNode()
        initial = node.current_concurrent
        
        # Simulate rate limit
        await node._on_rate_limit()
        
        expected = max(node.min_concurrent, int(initial * node.backoff_factor))
        assert node.current_concurrent == expected
        assert node.stats["total_rate_limits"] == 1
    
    @pytest.mark.asyncio
    async def test_multiple_backoffs(self):
        """Test multiple consecutive backoffs."""
        node = SimpleAdaptiveNode()
        node._current_concurrent = 10
        
        await node._on_rate_limit()  # 10 -> 5
        assert node.current_concurrent == 5
        
        await node._on_rate_limit()  # 5 -> 2
        assert node.current_concurrent == 2
        
        await node._on_rate_limit()  # 2 -> 1
        assert node.current_concurrent == 1
        
        await node._on_rate_limit()  # Should stay at min (1)
        assert node.current_concurrent == 1
    
    @pytest.mark.asyncio
    async def test_resets_consecutive_successes_on_backoff(self):
        """Test that consecutive successes reset on rate limit."""
        node = SimpleAdaptiveNode()
        node._consecutive_successes = 5
        
        await node._on_rate_limit()
        
        assert node._consecutive_successes == 0


class TestAdaptiveThrottledNodeRecovery:
    """Tests for recovery behavior after sustained success."""
    
    @pytest.mark.asyncio
    async def test_recovers_after_threshold(self):
        """Test that concurrency increases after recovery_threshold successes."""
        node = SimpleAdaptiveNode()
        node._current_concurrent = 5
        node.recovery_threshold = 3
        
        # Simulate successes
        for _ in range(3):
            await node._on_success()
        
        # Should have recovered: 5 * 2.0 = 10
        assert node.current_concurrent == 10
    
    @pytest.mark.asyncio
    async def test_does_not_exceed_max(self):
        """Test that recovery doesn't exceed max_concurrent."""
        node = SimpleAdaptiveNode()
        node._current_concurrent = 15
        node.max_concurrent = 20
        node.recovery_threshold = 1
        node.recovery_factor = 2.0
        
        await node._on_success()  # Would be 30, but capped at 20
        
        assert node.current_concurrent == 20
    
    @pytest.mark.asyncio
    async def test_resets_consecutive_counter_on_recovery(self):
        """Test that consecutive successes reset after recovery."""
        node = SimpleAdaptiveNode()
        node.recovery_threshold = 3
        
        for _ in range(3):
            await node._on_success()
        
        assert node._consecutive_successes == 0


class TestAdaptiveThrottledNodeReset:
    """Tests for reset functionality."""
    
    def test_reset_adaptive_state(self):
        """Test that reset_adaptive_state restores initial values."""
        node = SimpleAdaptiveNode()
        node._current_concurrent = 2
        node._consecutive_successes = 5
        node._total_rate_limits = 10
        node._total_successes = 50
        
        node.reset_adaptive_state()
        
        assert node.current_concurrent == node.initial_concurrent
        assert node._consecutive_successes == 0
        assert node._total_rate_limits == 0
        assert node._total_successes == 0


class TestAdaptiveThrottledNodeIntegration:
    """Integration tests for adaptive behavior."""
    
    @pytest.mark.asyncio
    async def test_successful_batch_increases_stats(self):
        """Test that successful batch processing updates stats."""
        node = SimpleAdaptiveNode()
        shared = {"items": [1, 2, 3, 4, 5]}
        
        await node._run_async(shared)
        
        assert node.stats["total_successes"] == 5
        assert node.stats["total_rate_limits"] == 0


# =============================================================================
# Performance Tests
# =============================================================================

class TestThrottledNodePerformance:
    """Performance and timing tests."""
    
    @pytest.mark.asyncio
    async def test_parallel_execution_speedup(self):
        """Verify that parallel execution is faster than sequential."""
        class SlowNode(ThrottledParallelBatchNode):
            max_concurrent = 10
            max_per_minute = None
            
            async def prep_async(self, shared):
                return shared["items"]
            
            async def exec_async(self, item):
                await asyncio.sleep(0.1)
                return item
            
            async def post_async(self, shared, prep_res, exec_res_list):
                shared["results"] = exec_res_list
                return "default"
        
        node = SlowNode()
        shared = {"items": list(range(10))}
        
        start = time.monotonic()
        await node._run_async(shared)
        elapsed = time.monotonic() - start
        
        # 10 items at 0.1s each, but with 10 concurrent
        # should complete in ~0.1-0.2s instead of 1.0s
        assert elapsed < 0.5, f"Parallel execution too slow: {elapsed}s"
        assert len(shared["results"]) == 10
