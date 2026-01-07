"""
Throttled Node Classes
======================

Drop-in replacements for PocketFlow's AsyncParallelBatchNode with built-in
rate limiting capabilities for LLM services and API calls.

Classes:
    - ThrottledParallelBatchNode: Fixed rate limiting
    - AdaptiveThrottledNode: Dynamic rate limiting that responds to API feedback
"""

import asyncio
from typing import Any, List, Optional, Union

from pocketflow import AsyncNode, BatchNode

from .rate_limiter import RateLimiter


class ThrottledParallelBatchNode(AsyncNode, BatchNode):
    """
    Parallel batch node with built-in rate limiting.
    
    A drop-in replacement for PocketFlow's AsyncParallelBatchNode that respects
    API rate limits. Executes items concurrently but with controlled parallelism
    to avoid overwhelming external services.
    
    Configuration can be set via:
    1. Class attributes (for subclasses)
    2. Constructor keyword arguments (for instances)
    
    Class Attributes:
        max_concurrent (int): Maximum simultaneous executions (default: 5)
        max_per_minute (int | None): Maximum executions per minute, None = unlimited (default: None)
    
    Example:
        ```python
        class TranslateNode(ThrottledParallelBatchNode):
            max_concurrent = 5      # Max 5 simultaneous API calls
            max_per_minute = 60     # Max 60 requests per minute
            
            async def prep_async(self, shared):
                return shared["texts"]
            
            async def exec_async(self, text):
                return await translate_api(text)
            
            async def post_async(self, shared, prep_res, exec_res_list):
                shared["translations"] = exec_res_list
                return "default"
        
        # Run with throttling
        node = TranslateNode()
        flow = AsyncFlow(start=node)
        await flow.run_async(shared)
        ```
    
    Note:
        Unlike AsyncParallelBatchNode which fires all requests immediately,
        this class queues requests and releases them according to the rate
        limit configuration, preventing 429 errors from external APIs.
    """
    
    # Default throttling configuration (can be overridden in subclasses)
    max_concurrent: int = 5
    max_per_minute: Optional[int] = None
    
    def __init__(
        self, 
        max_retries: int = 1, 
        wait: int = 0,
        *,
        max_concurrent: Optional[int] = None,
        max_per_minute: Optional[int] = None
    ):
        """
        Initialize the throttled parallel batch node.
        
        Args:
            max_retries: Maximum retry attempts for exec_async (default: 1, no retry)
            wait: Seconds to wait between retries (default: 0)
            max_concurrent: Override class-level max_concurrent setting
            max_per_minute: Override class-level max_per_minute setting
        """
        super().__init__(max_retries, wait)
        
        # Allow instance-level override of class defaults
        if max_concurrent is not None:
            self.max_concurrent = max_concurrent
        if max_per_minute is not None:
            self.max_per_minute = max_per_minute
        
        self._limiter: Optional[RateLimiter] = None
    
    @property
    def limiter(self) -> RateLimiter:
        """
        Lazy-initialized rate limiter.
        
        The limiter is created on first access to allow configuration
        to be set after instantiation but before execution.
        """
        if self._limiter is None:
            self._limiter = RateLimiter(
                max_concurrent=self.max_concurrent,
                max_per_window=self.max_per_minute,
                window_seconds=60.0
            )
        return self._limiter
    
    def reset_limiter(self) -> None:
        """
        Reset the rate limiter.
        
        Call this to clear rate limiting state between runs if needed.
        The limiter will be recreated on next use with current configuration.
        """
        self._limiter = None
    
    async def _throttled_exec(self, item: Any) -> Any:
        """
        Execute a single item with rate limiting applied.
        
        Acquires rate limit permission before executing and ensures
        the semaphore is released even if an exception occurs.
        """
        async with self.limiter:
            # Call parent's _exec which handles retries
            return await super(ThrottledParallelBatchNode, self)._exec(item)
    
    async def _exec(self, items: List[Any]) -> List[Any]:
        """
        Execute all items with controlled parallelism.
        
        Unlike AsyncParallelBatchNode which uses bare asyncio.gather,
        this wraps each execution with rate limiting.
        
        Args:
            items: List of items from prep_async to process
            
        Returns:
            List of results in the same order as input items
        """
        if not items:
            return []
        
        tasks = [self._throttled_exec(item) for item in items]
        return await asyncio.gather(*tasks)
    
    @staticmethod
    def is_rate_limit_error(exc: Exception) -> bool:
        """
        Check if an exception indicates a rate limit error.
        
        Override this method to customize rate limit detection for
        specific API clients or error types.
        
        Args:
            exc: The exception to check
            
        Returns:
            True if this appears to be a rate limit error
        """
        err_str = str(exc).lower()
        return any(indicator in err_str for indicator in [
            '429',
            'rate limit',
            'rate_limit',
            'too many requests',
            'quota exceeded',
            'throttl',
        ])


class AdaptiveThrottledNode(ThrottledParallelBatchNode):
    """
    Parallel batch node with adaptive rate limiting.
    
    Extends ThrottledParallelBatchNode with dynamic throttling that responds
    to API feedback. Automatically backs off when hitting rate limits and
    gradually recovers throughput when requests succeed.
    
    This is ideal for APIs with:
    - Unpredictable or undocumented rate limits
    - Varying limits based on load or time of day
    - Soft limits that allow occasional bursts
    
    Class Attributes:
        initial_concurrent (int): Starting concurrency level (default: 5)
        min_concurrent (int): Minimum concurrency floor (default: 1)
        max_concurrent (int): Maximum concurrency ceiling (default: 20)
        backoff_factor (float): Multiplier on rate limit hit (default: 0.5)
        recovery_threshold (int): Consecutive successes before recovery (default: 10)
        recovery_factor (float): Multiplier on recovery (default: 1.2)
    
    Example:
        ```python
        class EmbeddingNode(AdaptiveThrottledNode):
            initial_concurrent = 10  # Start optimistic
            min_concurrent = 2       # Never go below 2
            max_concurrent = 50      # Cap at 50
            
            async def exec_async(self, text):
                return await embedding_api(text)
        
        # The node will automatically tune its concurrency
        # based on success/failure patterns
        ```
    
    Behavior:
        - On rate limit error: Reduces concurrency by backoff_factor (default: halves)
        - On sustained success: Increases concurrency by recovery_factor after
          recovery_threshold consecutive successes (default: +20% after 10 successes)
    """
    
    # Adaptive throttling configuration
    initial_concurrent: int = 5
    min_concurrent: int = 1
    max_concurrent: int = 20
    backoff_factor: float = 0.5
    recovery_threshold: int = 10
    recovery_factor: float = 1.2
    
    def __init__(
        self,
        max_retries: int = 1,
        wait: int = 0,
        *,
        initial_concurrent: Optional[int] = None,
        min_concurrent: Optional[int] = None,
        max_concurrent: Optional[int] = None,
        backoff_factor: Optional[float] = None,
        recovery_threshold: Optional[int] = None,
        recovery_factor: Optional[float] = None,
        max_per_minute: Optional[int] = None,
    ):
        """
        Initialize the adaptive throttled node.
        
        Args:
            max_retries: Maximum retry attempts for exec_async
            wait: Seconds to wait between retries
            initial_concurrent: Starting concurrency level
            min_concurrent: Minimum concurrency floor
            max_concurrent: Maximum concurrency ceiling
            backoff_factor: Concurrency multiplier on rate limit (0-1)
            recovery_threshold: Successes needed before recovery
            recovery_factor: Concurrency multiplier on recovery (>1)
            max_per_minute: Optional fixed rate limit (requests per minute)
        """
        # Set adaptive config before parent init
        if initial_concurrent is not None:
            self.initial_concurrent = initial_concurrent
        if min_concurrent is not None:
            self.min_concurrent = min_concurrent
        if max_concurrent is not None:
            self.max_concurrent = max_concurrent
        if backoff_factor is not None:
            self.backoff_factor = backoff_factor
        if recovery_threshold is not None:
            self.recovery_threshold = recovery_threshold
        if recovery_factor is not None:
            self.recovery_factor = recovery_factor
        
        # Initialize parent with initial concurrency
        super().__init__(
            max_retries=max_retries,
            wait=wait,
            max_concurrent=self.initial_concurrent,
            max_per_minute=max_per_minute
        )
        
        self._current_concurrent = self.initial_concurrent
        self._consecutive_successes = 0
        self._adaptive_lock = asyncio.Lock()
        self._total_rate_limits = 0
        self._total_successes = 0
    
    @property
    def current_concurrent(self) -> int:
        """Current adaptive concurrency level."""
        return self._current_concurrent
    
    @property
    def stats(self) -> dict:
        """
        Get adaptive throttling statistics.
        
        Returns:
            Dict with current_concurrent, total_successes, total_rate_limits,
            and consecutive_successes counts.
        """
        return {
            "current_concurrent": self._current_concurrent,
            "total_successes": self._total_successes,
            "total_rate_limits": self._total_rate_limits,
            "consecutive_successes": self._consecutive_successes,
        }
    
    async def _on_rate_limit(self) -> None:
        """
        Handle rate limit event by reducing concurrency.
        
        Called internally when a rate limit error is detected.
        Reduces concurrency by backoff_factor down to min_concurrent.
        """
        async with self._adaptive_lock:
            old_concurrent = self._current_concurrent
            self._current_concurrent = max(
                self.min_concurrent,
                int(self._current_concurrent * self.backoff_factor)
            )
            self._consecutive_successes = 0
            self._total_rate_limits += 1
            
            # Recreate limiter with new concurrency
            if self._current_concurrent != old_concurrent:
                self._limiter = RateLimiter(
                    max_concurrent=self._current_concurrent,
                    max_per_window=self.max_per_minute,
                    window_seconds=60.0
                )
    
    async def _on_success(self) -> None:
        """
        Handle successful execution.
        
        Called internally after each successful exec_async.
        After recovery_threshold consecutive successes, increases
        concurrency by recovery_factor up to max_concurrent.
        """
        async with self._adaptive_lock:
            self._consecutive_successes += 1
            self._total_successes += 1
            
            if self._consecutive_successes >= self.recovery_threshold:
                old_concurrent = self._current_concurrent
                self._current_concurrent = min(
                    self.max_concurrent,
                    int(self._current_concurrent * self.recovery_factor)
                )
                self._consecutive_successes = 0
                
                # Recreate limiter with new concurrency
                if self._current_concurrent != old_concurrent:
                    self._limiter = RateLimiter(
                        max_concurrent=self._current_concurrent,
                        max_per_window=self.max_per_minute,
                        window_seconds=60.0
                    )
    
    async def _throttled_exec(self, item: Any) -> Any:
        """
        Execute with adaptive throttling.
        
        Wraps parent execution with success/failure tracking to
        dynamically adjust the rate limiter.
        """
        async with self.limiter:
            try:
                # Call grandparent's _exec to get proper retry behavior
                result = await super(ThrottledParallelBatchNode, self)._exec(item)
                await self._on_success()
                return result
            except Exception as e:
                if self.is_rate_limit_error(e):
                    await self._on_rate_limit()
                raise
    
    def reset_adaptive_state(self) -> None:
        """
        Reset all adaptive throttling state.
        
        Resets concurrency to initial level and clears all counters.
        """
        self._current_concurrent = self.initial_concurrent
        self._consecutive_successes = 0
        self._total_rate_limits = 0
        self._total_successes = 0
        self._limiter = None
