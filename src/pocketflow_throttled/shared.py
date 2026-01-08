"""
Shared Rate Limiters
====================

Registry for managing shared rate limiters across multiple nodes and flows.
Useful when multiple components need to respect the same global rate limit.
"""

from typing import Dict, Optional, Any

from .rate_limiter import RateLimiter


class LimiterRegistry:
    """
    Registry for shared rate limiters.
    
    Use when multiple nodes/flows need to share the same rate limit,
    e.g., all hitting the same API endpoint across different flows.
    
    This is a singleton-style class with class methods for global access.
    
    Example:
        ```python
        # Register shared limiter at app startup
        LimiterRegistry.register(
            "openai",
            max_concurrent=10,
            max_per_window=60
        )
        
        # Use in nodes via manual acquisition
        class MyNode(AsyncNode):
            async def exec_async(self, item):
                async with LimiterRegistry.get("openai"):
                    return await call_openai(item)
        
        # Or use get_or_create for lazy initialization
        class AnotherNode(AsyncNode):
            async def exec_async(self, item):
                limiter = LimiterRegistry.get_or_create(
                    "anthropic",
                    max_concurrent=5,
                    max_per_window=30
                )
                async with limiter:
                    return await call_anthropic(item)
        ```
    
    Thread Safety:
        The registry itself is not thread-safe for registration.
        Register limiters during application startup before spawning
        async tasks. The RateLimiter instances are async-safe.
    
    Note:
        Shared limiters are useful when:
        - Multiple independent nodes call the same API
        - Flows run in parallel but share API quotas
        - You need global rate limit coordination
    """
    
    _limiters: Dict[str, RateLimiter] = {}
    
    @classmethod
    def register(
        cls,
        name: str,
        max_concurrent: int = 5,
        max_per_window: Optional[int] = None,
        window_seconds: float = 60.0,
        replace: bool = False,
    ) -> RateLimiter:
        """
        Register a named shared limiter.
        
        Args:
            name: Unique identifier for the limiter
            max_concurrent: Maximum simultaneous operations
            max_per_window: Maximum operations per time window (None = unlimited)
            window_seconds: Time window duration in seconds
            replace: If True, replace existing limiter with same name
            
        Returns:
            The registered RateLimiter instance
            
        Raises:
            ValueError: If limiter already exists and replace=False
            
        Example:
            ```python
            # Register OpenAI limits
            LimiterRegistry.register(
                "openai-gpt4",
                max_concurrent=5,
                max_per_window=60,
                window_seconds=60.0
            )
            
            # Register with replacement
            LimiterRegistry.register(
                "openai-gpt4",
                max_concurrent=10,
                replace=True
            )
            ```
        """
        if name in cls._limiters and not replace:
            raise ValueError(
                f"Limiter '{name}' already exists. Use replace=True to override."
            )
        
        cls._limiters[name] = RateLimiter(
            max_concurrent=max_concurrent,
            max_per_window=max_per_window,
            window_seconds=window_seconds
        )
        return cls._limiters[name]
    
    @classmethod
    def get(cls, name: str) -> RateLimiter:
        """
        Get a registered limiter by name.
        
        Args:
            name: The limiter identifier
            
        Returns:
            The RateLimiter instance
            
        Raises:
            KeyError: If limiter not found
            
        Example:
            ```python
            async with LimiterRegistry.get("openai"):
                await call_openai()
            ```
        """
        if name not in cls._limiters:
            raise KeyError(
                f"Limiter '{name}' not found. Register it first with "
                f"LimiterRegistry.register('{name}', ...) or use get_or_create()."
            )
        return cls._limiters[name]
    
    @classmethod
    def get_or_create(
        cls,
        name: str,
        max_concurrent: int = 5,
        max_per_window: Optional[int] = None,
        window_seconds: float = 60.0,
    ) -> RateLimiter:
        """
        Get existing limiter or create new one if not exists.
        
        This is useful for lazy initialization where you want to ensure
        a limiter exists without knowing if it was already registered.
        
        Args:
            name: Unique identifier for the limiter
            max_concurrent: Maximum simultaneous operations (if creating)
            max_per_window: Maximum operations per window (if creating)
            window_seconds: Time window duration (if creating)
            
        Returns:
            Existing or newly created RateLimiter
            
        Note:
            If the limiter already exists, the provided configuration
            is ignored and the existing limiter is returned unchanged.
            
        Example:
            ```python
            # Safe to call multiple times - creates once, reuses after
            limiter = LimiterRegistry.get_or_create("my-api", max_concurrent=10)
            async with limiter:
                await call_api()
            ```
        """
        if name not in cls._limiters:
            cls.register(name, max_concurrent, max_per_window, window_seconds)
        return cls._limiters[name]
    
    @classmethod
    def remove(cls, name: str) -> bool:
        """
        Remove a limiter from the registry.
        
        Args:
            name: The limiter identifier to remove
            
        Returns:
            True if removed, False if not found
            
        Example:
            ```python
            LimiterRegistry.remove("old-api")
            ```
        """
        if name in cls._limiters:
            del cls._limiters[name]
            return True
        return False
    
    @classmethod
    def reset(cls, name: Optional[str] = None) -> None:
        """
        Reset one or all limiters.
        
        If name is provided, removes that specific limiter.
        If name is None, clears the entire registry.
        
        Args:
            name: Optional specific limiter to reset, or None for all
            
        Example:
            ```python
            # Reset single limiter
            LimiterRegistry.reset("openai")
            
            # Reset all limiters
            LimiterRegistry.reset()
            ```
        """
        if name is None:
            cls._limiters.clear()
        elif name in cls._limiters:
            del cls._limiters[name]
    
    @classmethod
    def exists(cls, name: str) -> bool:
        """
        Check if a limiter is registered.
        
        Args:
            name: The limiter identifier
            
        Returns:
            True if limiter exists
        """
        return name in cls._limiters
    
    @classmethod
    def list_names(cls) -> list:
        """
        Get list of all registered limiter names.
        
        Returns:
            List of limiter names
        """
        return list(cls._limiters.keys())
    
    @classmethod
    def list_all(cls) -> Dict[str, Dict[str, Any]]:
        """
        List all registered limiters with their configurations.
        
        Returns:
            Dict mapping limiter names to their configuration dicts
            
        Example:
            ```python
            for name, config in LimiterRegistry.list_all().items():
                print(f"{name}: {config}")
            # openai: {'max_concurrent': 5, 'max_per_window': 60, ...}
            ```
        """
        return {
            name: {
                "max_concurrent": lim._max_concurrent,
                "max_per_window": lim._max_per_window,
                "window_seconds": lim._window_seconds,
            }
            for name, lim in cls._limiters.items()
        }
    
    @classmethod
    def stats(cls, name: str) -> Dict[str, Any]:
        """
        Get current statistics for a limiter.
        
        Args:
            name: The limiter identifier
            
        Returns:
            Dict with current usage statistics
            
        Raises:
            KeyError: If limiter not found
        """
        limiter = cls.get(name)
        return {
            "max_concurrent": limiter._max_concurrent,
            "max_per_window": limiter._max_per_window,
            "window_seconds": limiter._window_seconds,
            "current_window_count": len(limiter._timestamps),
        }
