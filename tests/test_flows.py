"""
Tests for Throttled Flow Classes
================================

Tests for ThrottledAsyncParallelBatchFlow and AdaptiveThrottledBatchFlow.
"""

import asyncio
import pytest
import time
from typing import Any, Dict, List

from pocketflow import AsyncNode

from pocketflow_throttled import (
    ThrottledAsyncParallelBatchFlow,
    AdaptiveThrottledBatchFlow,
    RateLimitHit,
)


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================

class SimpleProcessNode(AsyncNode):
    """Simple node that tracks execution."""
    
    executions: List[int] = []
    
    async def exec_async(self, _):
        user_id = self.params.get("user_id", 0)
        SimpleProcessNode.executions.append(user_id)
        await asyncio.sleep(0.01)  # Small delay
        return f"processed_{user_id}"
    
    async def post_async(self, shared, prep_res, exec_res):
        shared.setdefault("results", []).append(exec_res)
        return "default"
    
    @classmethod
    def reset(cls):
        cls.executions = []


class SlowNode(AsyncNode):
    """Node with configurable delay."""
    
    delay: float = 0.1
    
    async def exec_async(self, _):
        await asyncio.sleep(self.delay)
        return self.params.get("user_id", 0)


class RateLimitNode(AsyncNode):
    """Node that raises RateLimitHit on certain conditions."""
    
    rate_limit_on: List[int] = []  # User IDs that trigger rate limit
    
    async def exec_async(self, _):
        user_id = self.params.get("user_id", 0)
        if user_id in RateLimitNode.rate_limit_on:
            raise RateLimitHit(f"Rate limit for user {user_id}")
        await asyncio.sleep(0.01)
        return f"processed_{user_id}"
    
    @classmethod
    def reset(cls):
        cls.rate_limit_on = []


# =============================================================================
# Tests for ThrottledAsyncParallelBatchFlow
# =============================================================================

class TestThrottledAsyncParallelBatchFlow:
    """Tests for ThrottledAsyncParallelBatchFlow."""
    
    @pytest.fixture(autouse=True)
    def reset_nodes(self):
        """Reset node state before each test."""
        SimpleProcessNode.reset()
        RateLimitNode.reset()
        yield
    
    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """Test basic flow execution with throttling."""
        class TestFlow(ThrottledAsyncParallelBatchFlow):
            max_concurrent_flows = 5
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(10)]
        
        flow = TestFlow(start=SimpleProcessNode())
        shared = {}
        await flow.run_async(shared)
        
        assert flow.stats["completed_flows"] == 10
        assert flow.stats["failed_flows"] == 0
        assert len(SimpleProcessNode.executions) == 10
    
    @pytest.mark.asyncio
    async def test_respects_max_concurrent(self):
        """Test that max_concurrent_flows is respected."""
        max_concurrent = 3
        concurrent_count = []
        current_concurrent = 0
        lock = asyncio.Lock()
        
        class TrackingNode(AsyncNode):
            async def exec_async(self, _):
                nonlocal current_concurrent
                async with lock:
                    current_concurrent += 1
                    concurrent_count.append(current_concurrent)
                
                await asyncio.sleep(0.05)
                
                async with lock:
                    current_concurrent -= 1
                
                return "done"
        
        class TestFlow(ThrottledAsyncParallelBatchFlow):
            max_concurrent_flows = max_concurrent
            
            async def prep_async(self, shared):
                return [{"id": i} for i in range(10)]
        
        flow = TestFlow(start=TrackingNode())
        await flow.run_async({})
        
        # Check that we never exceeded max_concurrent
        assert max(concurrent_count) <= max_concurrent
    
    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Test that stats are properly tracked."""
        class TestFlow(ThrottledAsyncParallelBatchFlow):
            max_concurrent_flows = 5
            max_flows_per_minute = 100
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(5)]
        
        flow = TestFlow(start=SimpleProcessNode())
        await flow.run_async({})
        
        stats = flow.stats
        assert stats["max_concurrent_flows"] == 5
        assert stats["max_flows_per_minute"] == 100
        assert stats["completed_flows"] == 5
        assert stats["failed_flows"] == 0
    
    @pytest.mark.asyncio
    async def test_handles_exceptions(self):
        """Test that exceptions are handled gracefully."""
        class FailingNode(AsyncNode):
            async def exec_async(self, _):
                user_id = self.params.get("user_id", 0)
                if user_id == 5:
                    raise ValueError("Intentional error")
                return f"done_{user_id}"
        
        class TestFlow(ThrottledAsyncParallelBatchFlow):
            max_concurrent_flows = 5
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(10)]
        
        flow = TestFlow(start=FailingNode())
        await flow.run_async({})  # Should not raise
        
        # One should fail
        assert flow.stats["failed_flows"] == 1
        assert flow.stats["completed_flows"] == 9
    
    @pytest.mark.asyncio
    async def test_constructor_kwargs(self):
        """Test configuration via constructor kwargs."""
        class TestFlow(ThrottledAsyncParallelBatchFlow):
            async def prep_async(self, shared):
                return [{"id": i} for i in range(3)]
        
        flow = TestFlow(
            start=SimpleProcessNode(),
            max_concurrent_flows=10,
            max_flows_per_minute=200,
        )
        
        assert flow.max_concurrent_flows == 10
        assert flow.max_flows_per_minute == 200
    
    @pytest.mark.asyncio
    async def test_reset_flow_limiter(self):
        """Test resetting the flow limiter."""
        class TestFlow(ThrottledAsyncParallelBatchFlow):
            max_concurrent_flows = 5
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(5)]
        
        flow = TestFlow(start=SimpleProcessNode())
        
        # Run once
        await flow.run_async({})
        assert flow.stats["completed_flows"] == 5
        
        # Reset
        flow.reset_flow_limiter()
        assert flow.stats["completed_flows"] == 0
        
        # Run again
        SimpleProcessNode.reset()
        await flow.run_async({})
        assert flow.stats["completed_flows"] == 5


# =============================================================================
# Tests for AdaptiveThrottledBatchFlow
# =============================================================================

class TestAdaptiveThrottledBatchFlow:
    """Tests for AdaptiveThrottledBatchFlow."""
    
    @pytest.fixture(autouse=True)
    def reset_nodes(self):
        """Reset node state before each test."""
        SimpleProcessNode.reset()
        RateLimitNode.reset()
        yield
    
    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """Test basic adaptive flow execution."""
        class TestFlow(AdaptiveThrottledBatchFlow):
            initial_concurrent_flows = 5
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(10)]
        
        flow = TestFlow(start=SimpleProcessNode())
        await flow.run_async({})
        
        assert flow.stats["completed_flows"] == 10
        assert flow.stats["failed_flows"] == 0
    
    @pytest.mark.asyncio
    async def test_backs_off_on_rate_limit(self):
        """Test that concurrency is reduced on RateLimitHit."""
        RateLimitNode.rate_limit_on = [0, 1, 2]  # First 3 trigger rate limit
        
        class TestFlow(AdaptiveThrottledBatchFlow):
            initial_concurrent_flows = 10
            min_concurrent_flows = 2
            backoff_factor = 0.5
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(20)]
        
        flow = TestFlow(start=RateLimitNode())
        await flow.run_async({})
        
        # Should have backed off due to rate limits
        assert flow.stats["total_rate_limits"] > 0
        # Concurrency should have decreased
        assert flow.current_concurrent_flows < 10
    
    @pytest.mark.asyncio
    async def test_recovers_after_success(self):
        """Test that concurrency recovers after sustained success."""
        class TestFlow(AdaptiveThrottledBatchFlow):
            initial_concurrent_flows = 5
            min_concurrent_flows = 2
            max_concurrent_flows = 20
            recovery_threshold = 5
            recovery_factor = 2.0  # Double on recovery
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(20)]
        
        flow = TestFlow(start=SimpleProcessNode())
        await flow.run_async({})
        
        # After 20 successes with threshold of 5, should have recovered
        # multiple times (20 / 5 = 4 recovery events)
        # 5 -> 10 -> 20 (capped at max)
        assert flow.current_concurrent_flows == 20  # Capped at max
    
    @pytest.mark.asyncio
    async def test_respects_min_concurrent(self):
        """Test that backoff doesn't go below min_concurrent_flows."""
        # All users trigger rate limit
        RateLimitNode.rate_limit_on = list(range(100))
        
        class TestFlow(AdaptiveThrottledBatchFlow):
            initial_concurrent_flows = 10
            min_concurrent_flows = 3
            backoff_factor = 0.5
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(50)]
        
        flow = TestFlow(start=RateLimitNode())
        await flow.run_async({})
        
        # Should not go below min
        assert flow.current_concurrent_flows >= 3
    
    @pytest.mark.asyncio
    async def test_respects_max_concurrent(self):
        """Test that recovery doesn't exceed max_concurrent_flows."""
        class TestFlow(AdaptiveThrottledBatchFlow):
            initial_concurrent_flows = 5
            max_concurrent_flows = 8
            recovery_threshold = 2
            recovery_factor = 2.0
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(20)]
        
        flow = TestFlow(start=SimpleProcessNode())
        await flow.run_async({})
        
        # Should not exceed max
        assert flow.current_concurrent_flows <= 8
    
    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Test that adaptive stats are tracked."""
        RateLimitNode.rate_limit_on = [5]  # One rate limit
        
        class TestFlow(AdaptiveThrottledBatchFlow):
            initial_concurrent_flows = 5
            recovery_threshold = 10
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(10)]
        
        flow = TestFlow(start=RateLimitNode())
        await flow.run_async({})
        
        stats = flow.stats
        assert "current_concurrent_flows" in stats
        assert "consecutive_successes" in stats
        assert "total_rate_limits" in stats
        assert stats["total_rate_limits"] == 1
    
    @pytest.mark.asyncio
    async def test_reset_adaptive_state(self):
        """Test resetting adaptive state."""
        RateLimitNode.rate_limit_on = [0, 1, 2]
        
        class TestFlow(AdaptiveThrottledBatchFlow):
            initial_concurrent_flows = 10
            min_concurrent_flows = 2
            backoff_factor = 0.5
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(10)]
        
        flow = TestFlow(start=RateLimitNode())
        await flow.run_async({})
        
        # Should have backed off
        backed_off_level = flow.current_concurrent_flows
        assert backed_off_level < 10
        
        # Reset
        flow.reset_adaptive_state()
        assert flow.current_concurrent_flows == 10
        assert flow.stats["total_rate_limits"] == 0
        assert flow.stats["consecutive_successes"] == 0
    
    @pytest.mark.asyncio
    async def test_constructor_kwargs(self):
        """Test configuration via constructor kwargs."""
        class TestFlow(AdaptiveThrottledBatchFlow):
            async def prep_async(self, shared):
                return []
        
        flow = TestFlow(
            start=SimpleProcessNode(),
            initial_concurrent_flows=15,
            min_concurrent_flows=3,
            max_concurrent_flows=30,
            backoff_factor=0.6,
            recovery_threshold=8,
            recovery_factor=1.5,
        )
        
        assert flow.initial_concurrent_flows == 15
        assert flow.min_concurrent_flows == 3
        assert flow.max_concurrent_flows == 30
        assert flow.backoff_factor == 0.6
        assert flow.recovery_threshold == 8
        assert flow.recovery_factor == 1.5


# =============================================================================
# Integration Tests
# =============================================================================

class TestFlowIntegration:
    """Integration tests for throttled flows."""
    
    @pytest.fixture(autouse=True)
    def reset_nodes(self):
        SimpleProcessNode.reset()
        yield
    
    @pytest.mark.asyncio
    async def test_nested_throttling(self):
        """Test flow throttling with throttled nodes inside."""
        from pocketflow_throttled import ThrottledParallelBatchNode
        
        class ThrottledNode(ThrottledParallelBatchNode):
            max_concurrent = 2
            
            async def prep_async(self, shared):
                user_id = self.params.get("user_id", 0)
                return [f"{user_id}_item_{i}" for i in range(5)]
            
            async def exec_async(self, item):
                await asyncio.sleep(0.01)
                return f"processed_{item}"
            
            async def post_async(self, shared, prep_res, exec_res_list):
                shared.setdefault("all_results", []).extend(exec_res_list)
                return "default"
        
        class TestFlow(ThrottledAsyncParallelBatchFlow):
            max_concurrent_flows = 3
            
            async def prep_async(self, shared):
                return [{"user_id": i} for i in range(5)]
        
        flow = TestFlow(start=ThrottledNode())
        shared = {"all_results": []}
        await flow.run_async(shared)
        
        # 5 users × 5 items = 25 total results
        assert len(shared["all_results"]) == 25
        assert flow.stats["completed_flows"] == 5
