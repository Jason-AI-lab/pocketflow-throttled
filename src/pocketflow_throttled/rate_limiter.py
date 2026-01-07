"""
Rate Limiter Module
===================

A lightweight token bucket rate limiter with sliding window semantics.
Provides dual-mode throttling: concurrency (semaphore) + throughput (sliding window).

Zero external dependencies - uses only Python standard library.
"""

import asyncio
import time
from collections import deque
from typing import Optional


class RateLimiter:
    """
    Token bucket rate limiter with sliding window for async operations.
    
    Provides two complementary throttling mechanisms:
    1. **Concurrency limiting** (semaphore): Max simultaneous operations
    2. **Throughput limiting** (sliding window): Max operations per time window
    
    Args:
        max_concurrent: Maximum simultaneous operations (default: 5)
        max_per_window: Maximum operations per time window, None = unlimited (default: None)
        window_seconds: Time window duration in seconds (default: 60)
    
    Example:
        ```python
        # Allow max 5 concurrent requests, 60 requests per minute
        limiter = RateLimiter(max_concurrent=5, max_per_window=60)
        
        async def make_api_call():
            async with limiter:
                response = await api.call()
            return response
        
        # All calls will be throttled automatically
        results = await asyncio.gather(*[make_api_call() for _ in range(100)])
        ```
    
    Note:
        The sliding window algorithm ensures smooth rate limiting by tracking
        individual request timestamps rather than fixed time buckets. This
        prevents burst behavior at window boundaries.
    """
    
    def __init__(
        self, 
        max_concurrent: int = 5, 
        max_per_window: Optional[int] = None, 
        window_seconds: float = 60.0
    ):
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        if max_per_window is not None and max_per_window < 1:
            raise ValueError("max_per_window must be at least 1 or None")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        
        self._max_concurrent = max_concurrent
        self._max_per_window = max_per_window
        self._window_seconds = window_seconds
        
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timestamps: deque = deque()
        self._lock = asyncio.Lock()
    
    @property
    def max_concurrent(self) -> int:
        """Maximum simultaneous operations allowed."""
        return self._max_concurrent
    
    @property
    def max_per_window(self) -> Optional[int]:
        """Maximum operations per time window (None = unlimited)."""
        return self._max_per_window
    
    @property
    def window_seconds(self) -> float:
        """Time window duration in seconds."""
        return self._window_seconds
    
    @property
    def current_window_count(self) -> int:
        """Number of operations in the current sliding window."""
        now = time.monotonic()
        return sum(1 for ts in self._timestamps if now - ts <= self._window_seconds)
    
    async def acquire(self) -> None:
        """
        Acquire permission to proceed, waiting if rate limited.
        
        This method will block (await) until both conditions are satisfied:
        1. A semaphore slot is available (concurrency limit)
        2. The sliding window has capacity (throughput limit)
        
        Raises:
            asyncio.CancelledError: If the waiting coroutine is cancelled
        """
        # First, acquire semaphore (concurrency limit)
        await self._semaphore.acquire()
        
        # Then, check sliding window (throughput limit)
        if self._max_per_window is not None:
            async with self._lock:
                now = time.monotonic()
                
                # Evict timestamps outside the sliding window
                while self._timestamps and now - self._timestamps[0] > self._window_seconds:
                    self._timestamps.popleft()
                
                # If at capacity, wait for the oldest request to expire
                if len(self._timestamps) >= self._max_per_window:
                    sleep_time = self._window_seconds - (now - self._timestamps[0]) + 0.001
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                        # Re-evict after sleeping (time has passed)
                        now = time.monotonic()
                        while self._timestamps and now - self._timestamps[0] > self._window_seconds:
                            self._timestamps.popleft()
                
                # Record this request's timestamp
                self._timestamps.append(time.monotonic())
    
    def release(self) -> None:
        """
        Release the semaphore after operation completes.
        
        Must be called after acquire() to free the concurrency slot.
        Using the context manager (async with) handles this automatically.
        """
        self._semaphore.release()
    
    async def __aenter__(self) -> "RateLimiter":
        """Async context manager entry - acquires rate limit permission."""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - releases semaphore."""
        self.release()
    
    def reset(self) -> None:
        """
        Reset the rate limiter state.
        
        Clears the sliding window timestamps. Does not affect
        currently held semaphore slots.
        """
        self._timestamps.clear()
    
    def __repr__(self) -> str:
        return (
            f"RateLimiter(max_concurrent={self._max_concurrent}, "
            f"max_per_window={self._max_per_window}, "
            f"window_seconds={self._window_seconds})"
        )
