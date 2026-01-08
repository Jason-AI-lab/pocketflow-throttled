"""
Throttled Flow Classes
======================

Rate-limited extensions for PocketFlow's AsyncParallelBatchFlow that control
how many flow instances run concurrently.

Classes:
    - ThrottledAsyncParallelBatchFlow: Fixed rate limiting for parallel flows
    - AdaptiveThrottledBatchFlow: Dynamic rate limiting that responds to errors
"""

import asyncio
from typing import Any, Dict, List, Optional

from pocketflow import AsyncParallelBatchFlow, AsyncNode

from .rate_limiter import RateLimiter
from .exceptions import RateLimitHit


class ThrottledAsyncParallelBatchFlow(AsyncParallelBatchFlow):
    """
    AsyncParallelBatchFlow with rate-limited parallel execution.
    
    Controls how many flow instances run concurrently, preventing
    resource exhaustion when processing large batches. Each flow
    instance runs the entire node graph with different parameters.
    
    This is useful when:
    - Processing many items in parallel (users, documents, etc.)
    - Each item requires multiple API calls (multi-node flows)
    - You need to limit total concurrent operations across all items
    
    Class Attributes:
        max_concurrent_flows (int): Maximum simultaneous flow instances (default: 5)
        max_flows_per_minute (int | None): Optional throughput limit (default: None)
    
    Example:
        ```python
        from pocketflow import AsyncNode
        from pocketflow_throttled import ThrottledAsyncParallelBatchFlow
        
        class FetchUserNode(AsyncNode):
            async def exec_async(self, _):
                user_id = self.params["user_id"]
                return await fetch_user(user_id)
        
        class ProcessUsersFlow(ThrottledAsyncParallelBatchFlow):
            max_concurrent_flows = 10  # Max 10 users processed in parallel
            max_flows_per_minute = 60  # Max 60 users started per minute
            
            async def prep_async(self, shared):
                return [{"user_id": uid} for uid in shared["user_ids"]]
        
        flow = ProcessUsersFlow(start=FetchUserNode())
        await flow.run_async({"user_ids": range(1000)})  # Processes 10 at a time
        print(flow.stats)
        ```
    
    Comparison with ThrottledParallelBatchNode:
        - ThrottledParallelBatchNode: Limits items within a single node
        - ThrottledAsyncParallelBatchFlow: Limits flow instances across entire graph
        
        Use both together for fine-grained control:
        ```python
        class MyFlow(ThrottledAsyncParallelBatchFlow):
            max_concurrent_flows = 5  # 5 users at once
        
        class MyNode(ThrottledParallelBatchNode):
            max_concurrent = 3  # 3 API calls per user at once
        
        # Effective limit: 5 users × 3 calls = 15 max concurrent API calls
        ```
    
    Note:
        All parallel flow instances share the same `shared` dict.
        Use `self.params` for flow-specific data to avoid race conditions.
    """
    
    max_concurrent_flows: int = 5
    max_flows_per_minute: Optional[int] = None
    
    def __init__(
        self,
        start=None,
        *,
        max_concurrent_flows: Optional[int] = None,
        max_flows_per_minute: Optional[int] = None,
    ):
        """
        Initialize the throttled parallel batch flow.
        
        Args:
            start: Starting node for the flow
            max_concurrent_flows: Override class-level max_concurrent_flows
            max_flows_per_minute: Override class-level max_flows_per_minute
        """
        super().__init__(start=start)
        
        if max_concurrent_flows is not None:
            self.max_concurrent_flows = max_concurrent_flows
        if max_flows_per_minute is not None:
            self.max_flows_per_minute = max_flows_per_minute
        
        self._flow_limiter: Optional[RateLimiter] = None
        self._completed_flows: int = 0
        self._failed_flows: int = 0
        self._flow_results: List[Any] = []
    
    @property
    def flow_limiter(self) -> RateLimiter:
        """
        Lazy-initialized flow rate limiter.
        
        The limiter is created on first access to allow configuration
        to be set after instantiation but before execution.
        """
        if self._flow_limiter is None:
            self._flow_limiter = RateLimiter(
                max_concurrent=self.max_concurrent_flows,
                max_per_window=self.max_flows_per_minute,
                window_seconds=60.0
            )
        return self._flow_limiter
    
    def reset_flow_limiter(self) -> None:
        """
        Reset the flow limiter and statistics.
        
        Call this to clear rate limiting state between runs if needed.
        """
        self._flow_limiter = None
        self._completed_flows = 0
        self._failed_flows = 0
        self._flow_results = []
    
    @property
    def stats(self) -> Dict[str, Any]:
        """
        Get current flow execution statistics.
        
        Returns:
            Dict containing:
            - max_concurrent_flows: Configured concurrency limit
            - max_flows_per_minute: Configured throughput limit
            - completed_flows: Number of successfully completed flows
            - failed_flows: Number of failed flow instances
        """
        return {
            "max_concurrent_flows": self.max_concurrent_flows,
            "max_flows_per_minute": self.max_flows_per_minute,
            "completed_flows": self._completed_flows,
            "failed_flows": self._failed_flows,
        }
    
    async def _run_async(self, shared: Dict[str, Any]) -> Any:
        """
        Run all flow instances with throttling.
        
        Overrides parent to wrap each flow instance with rate limiting.
        """
        pr = await self.prep_async(shared) or []
        
        # Reset stats for this run
        self._completed_flows = 0
        self._failed_flows = 0
        self._flow_results = []
        
        async def run_throttled(bp: Dict[str, Any]) -> Any:
            """Run a single flow instance with rate limiting."""
            async with self.flow_limiter:
                try:
                    result = await self._orch_async(shared, {**self.params, **bp})
                    self._completed_flows += 1
                    return result
                except Exception as e:
                    self._failed_flows += 1
                    raise
        
        # Run all flow instances with throttling
        results = await asyncio.gather(
            *(run_throttled(bp) for bp in pr),
            return_exceptions=True  # Don't fail all on one error
        )
        
        self._flow_results = results
        return await self.post_async(shared, pr, results)


class AdaptiveThrottledBatchFlow(ThrottledAsyncParallelBatchFlow):
    """
    AsyncParallelBatchFlow with adaptive rate limiting.
    
    Automatically adjusts concurrent flow count based on rate limit
    signals from child nodes. When a flow instance raises RateLimitHit,
    the flow reduces concurrency. After sustained success, it recovers.
    
    This is ideal for:
    - APIs with unpredictable or dynamic rate limits
    - Systems where optimal concurrency varies by load
    - Long-running batch jobs that need to self-tune
    
    Class Attributes:
        initial_concurrent_flows (int): Starting concurrency (default: 5)
        min_concurrent_flows (int): Floor for backoff (default: 1)
        max_concurrent_flows (int): Ceiling for recovery (default: 20)
        backoff_factor (float): Multiplier on rate limit (default: 0.5)
        recovery_threshold (int): Successes before recovery (default: 10)
        recovery_factor (float): Multiplier on recovery (default: 1.2)
    
    Example:
        ```python
        from pocketflow_throttled import AdaptiveThrottledBatchFlow, RateLimitHit
        
        class APINode(AsyncNode):
            async def exec_async(self, _):
                try:
                    return await call_flaky_api()
                except TooManyRequestsError:
                    raise RateLimitHit()  # Signal to flow
        
        class SmartUserFlow(AdaptiveThrottledBatchFlow):
            initial_concurrent_flows = 20   # Start aggressive
            min_concurrent_flows = 2        # Don't go below 2
            max_concurrent_flows = 50       # Cap at 50
            backoff_factor = 0.5            # Halve on rate limit
            recovery_threshold = 20         # 20 successes to recover
            recovery_factor = 1.3           # +30% on recovery
            
            async def prep_async(self, shared):
                return [{"user_id": uid} for uid in shared["user_ids"]]
        
        flow = SmartUserFlow(start=APINode())
        await flow.run_async({"user_ids": range(1000)})
        
        print(flow.stats)
        # {'current_concurrent_flows': 12, 'total_rate_limits': 5, ...}
        ```
    
    Rate Limit Detection:
        The flow detects rate limits when child nodes raise RateLimitHit.
        Use this in your nodes:
        ```python
        from pocketflow_throttled import RateLimitHit
        
        class MyNode(AsyncNode):
            async def exec_async(self, item):
                try:
                    return await api_call(item)
                except APIRateLimitError:
                    raise RateLimitHit()
        ```
        
        Or use AdaptiveThrottledNode with propagate_rate_limit=True.
    
    Behavior:
        - On RateLimitHit: Reduces concurrency by backoff_factor
        - After recovery_threshold successes: Increases by recovery_factor
        - Always stays within [min_concurrent_flows, max_concurrent_flows]
    """
    
    initial_concurrent_flows: int = 5
    min_concurrent_flows: int = 1
    max_concurrent_flows: int = 20  # Acts as ceiling for adaptive scaling
    backoff_factor: float = 0.5
    recovery_threshold: int = 10
    recovery_factor: float = 1.2
    
    def __init__(
        self,
        start=None,
        *,
        initial_concurrent_flows: Optional[int] = None,
        min_concurrent_flows: Optional[int] = None,
        max_concurrent_flows: Optional[int] = None,
        backoff_factor: Optional[float] = None,
        recovery_threshold: Optional[int] = None,
        recovery_factor: Optional[float] = None,
        max_flows_per_minute: Optional[int] = None,
    ):
        """
        Initialize the adaptive throttled batch flow.
        
        Args:
            start: Starting node for the flow
            initial_concurrent_flows: Starting concurrency level
            min_concurrent_flows: Minimum concurrency floor
            max_concurrent_flows: Maximum concurrency ceiling
            backoff_factor: Concurrency multiplier on rate limit (0-1)
            recovery_threshold: Successes needed before recovery
            recovery_factor: Concurrency multiplier on recovery (>1)
            max_flows_per_minute: Optional fixed rate limit
        """
        # Set adaptive config BEFORE parent init
        if initial_concurrent_flows is not None:
            self.initial_concurrent_flows = initial_concurrent_flows
        if min_concurrent_flows is not None:
            self.min_concurrent_flows = min_concurrent_flows
        if max_concurrent_flows is not None:
            self.max_concurrent_flows = max_concurrent_flows
        if backoff_factor is not None:
            self.backoff_factor = backoff_factor
        if recovery_threshold is not None:
            self.recovery_threshold = recovery_threshold
        if recovery_factor is not None:
            self.recovery_factor = recovery_factor
        
        # Initialize adaptive state BEFORE super().__init__()
        self._current_concurrent_flows = self.initial_concurrent_flows
        self._consecutive_successes = 0
        self._adaptive_lock = asyncio.Lock()
        self._total_rate_limits = 0
        
        # Initialize parent (don't pass max_concurrent_flows, we override limiter)
        super().__init__(
            start=start,
            max_flows_per_minute=max_flows_per_minute,
        )
    
    @property
    def flow_limiter(self) -> RateLimiter:
        """
        Override to use adaptive concurrent value.
        
        Uses _current_concurrent_flows instead of max_concurrent_flows
        to support dynamic adjustment.
        """
        if self._flow_limiter is None:
            self._flow_limiter = RateLimiter(
                max_concurrent=self._current_concurrent_flows,
                max_per_window=self.max_flows_per_minute,
                window_seconds=60.0
            )
        return self._flow_limiter
    
    @property
    def current_concurrent_flows(self) -> int:
        """Current adaptive concurrency level."""
        return self._current_concurrent_flows
    
    @property
    def stats(self) -> Dict[str, Any]:
        """
        Get adaptive throttling statistics.
        
        Returns:
            Dict containing all parent stats plus:
            - current_concurrent_flows: Current adaptive level
            - consecutive_successes: Successes since last rate limit
            - total_rate_limits: Total rate limits encountered
        """
        base = super().stats
        base.update({
            "current_concurrent_flows": self._current_concurrent_flows,
            "consecutive_successes": self._consecutive_successes,
            "total_rate_limits": self._total_rate_limits,
        })
        return base
    
    async def _on_rate_limit(self, exc: Optional[RateLimitHit] = None) -> None:
        """
        Handle rate limit event by reducing concurrency.
        
        Called internally when a flow instance raises RateLimitHit.
        Reduces concurrency by backoff_factor down to min_concurrent_flows.
        
        Args:
            exc: The RateLimitHit exception (may contain retry_after hint)
        """
        async with self._adaptive_lock:
            old = self._current_concurrent_flows
            self._current_concurrent_flows = max(
                self.min_concurrent_flows,
                int(self._current_concurrent_flows * self.backoff_factor)
            )
            self._consecutive_successes = 0
            self._total_rate_limits += 1
            
            # Reset limiter if concurrency changed
            if self._current_concurrent_flows != old:
                self._flow_limiter = None
    
    async def _on_success(self) -> None:
        """
        Handle successful flow completion.
        
        Called internally after each successful flow instance.
        After recovery_threshold consecutive successes, increases
        concurrency by recovery_factor up to max_concurrent_flows.
        """
        async with self._adaptive_lock:
            self._consecutive_successes += 1
            
            if self._consecutive_successes >= self.recovery_threshold:
                old = self._current_concurrent_flows
                self._current_concurrent_flows = min(
                    self.max_concurrent_flows,
                    int(self._current_concurrent_flows * self.recovery_factor)
                )
                self._consecutive_successes = 0
                
                # Reset limiter if concurrency changed
                if self._current_concurrent_flows != old:
                    self._flow_limiter = None
    
    async def _run_async(self, shared: Dict[str, Any]) -> Any:
        """
        Run all flow instances with adaptive throttling.
        
        Overrides parent to add rate limit detection and adaptive behavior.
        """
        pr = await self.prep_async(shared) or []
        
        # Reset stats for this run
        self._completed_flows = 0
        self._failed_flows = 0
        self._flow_results = []
        
        async def run_adaptive(bp: Dict[str, Any]) -> Any:
            """Run a single flow instance with adaptive rate limiting."""
            async with self.flow_limiter:
                try:
                    result = await self._orch_async(shared, {**self.params, **bp})
                    self._completed_flows += 1
                    await self._on_success()
                    return result
                except RateLimitHit as e:
                    self._failed_flows += 1
                    await self._on_rate_limit(e)
                    raise
                except Exception:
                    self._failed_flows += 1
                    raise
        
        # Run all flow instances with adaptive throttling
        results = await asyncio.gather(
            *(run_adaptive(bp) for bp in pr),
            return_exceptions=True
        )
        
        self._flow_results = results
        return await self.post_async(shared, pr, results)
    
    def reset_adaptive_state(self) -> None:
        """
        Reset all adaptive throttling state.
        
        Resets concurrency to initial level and clears all counters.
        """
        self._current_concurrent_flows = self.initial_concurrent_flows
        self._consecutive_successes = 0
        self._total_rate_limits = 0
        self.reset_flow_limiter()
