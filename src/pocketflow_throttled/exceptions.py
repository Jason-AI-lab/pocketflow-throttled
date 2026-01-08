"""
Exception Classes
=================

Custom exceptions for signaling rate limit events between nodes and flows.
"""

from typing import Optional


class RateLimitHit(Exception):
    """
    Raised when a rate limit is encountered.
    
    Can be raised by nodes to signal to parent flows that
    throttling should be adjusted. Used by AdaptiveThrottledBatchFlow
    to detect rate limits and back off accordingly.
    
    Attributes:
        retry_after: Optional hint for how long to wait before retrying (seconds)
        source: Optional identifier of the rate limit source (e.g., "openai", "anthropic")
    
    Example:
        ```python
        class MyNode(AsyncNode):
            async def exec_async(self, item):
                try:
                    return await call_api(item)
                except APIRateLimitError as e:
                    # Signal to parent flow
                    raise RateLimitHit(
                        "OpenAI rate limit exceeded",
                        retry_after=e.retry_after,
                        source="openai"
                    )
        ```
    
    Note:
        When using AdaptiveThrottledNode with propagate_rate_limit=True,
        this exception is automatically raised when internal rate limit
        detection triggers.
    """
    
    def __init__(
        self, 
        message: str = "Rate limit hit",
        retry_after: Optional[float] = None,
        source: Optional[str] = None,
    ):
        """
        Initialize the rate limit exception.
        
        Args:
            message: Human-readable description of the rate limit
            retry_after: Optional seconds to wait before retrying
            source: Optional identifier for the rate limit source
        """
        super().__init__(message)
        self.retry_after = retry_after
        self.source = source
    
    def __repr__(self) -> str:
        parts = [f"RateLimitHit({self.args[0]!r}"]
        if self.retry_after is not None:
            parts.append(f", retry_after={self.retry_after}")
        if self.source is not None:
            parts.append(f", source={self.source!r}")
        parts.append(")")
        return "".join(parts)
