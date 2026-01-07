"""
PocketFlow Throttled - Rate-Limited Parallel Execution Extension
================================================================

A minimal extension for PocketFlow that provides rate-limited parallel execution
for LLM services, APIs, and web scraping tasks.

Features:
    - Dual-mode throttling: concurrency (semaphore) + throughput (sliding window)
    - Drop-in replacement for AsyncParallelBatchNode
    - Adaptive throttling that responds to rate limit errors
    - Pre-configured presets for popular LLM providers
    - Zero external dependencies beyond PocketFlow

Quick Start:
    ```python
    from pocketflow import AsyncFlow
    from pocketflow_throttled import ThrottledParallelBatchNode, Presets
    
    class TranslateNode(ThrottledParallelBatchNode):
        # Configure rate limits (OpenAI Tier 1: 60 RPM)
        max_concurrent = 5
        max_per_minute = 60
        
        async def prep_async(self, shared):
            return shared["texts"]
        
        async def exec_async(self, text):
            return await call_llm(f"Translate: {text}")
        
        async def post_async(self, shared, prep_res, exec_res_list):
            shared["translations"] = exec_res_list
            return "default"
    
    # Run with automatic throttling
    flow = AsyncFlow(start=TranslateNode())
    await flow.run_async({"texts": ["Hello", "World", ...]})
    ```

Classes:
    RateLimiter: Low-level rate limiter with sliding window algorithm
    ThrottledParallelBatchNode: Parallel batch node with fixed rate limits
    AdaptiveThrottledNode: Parallel batch node with dynamic rate limiting
    Presets: Pre-configured rate limits for popular services

For more information, see:
    - GitHub: https://github.com/your-repo/pocketflow-throttled
    - PocketFlow: https://github.com/The-Pocket/PocketFlow
"""

__version__ = "0.1.0"
__author__ = "Jason-AI-lab"

from .rate_limiter import RateLimiter
from .nodes import ThrottledParallelBatchNode, AdaptiveThrottledNode
from .presets import Presets, RateLimitConfig

__all__ = [
    # Version info
    "__version__",
    
    # Core classes
    "RateLimiter",
    "ThrottledParallelBatchNode",
    "AdaptiveThrottledNode",
    
    # Configuration
    "Presets",
    "RateLimitConfig",
]


def main() -> None:
    """CLI entry point - displays package info."""
    print(f"PocketFlow Throttled v{__version__}")
    print("=" * 40)
    print(__doc__)
    print("\nAvailable Presets:")
    for name, desc in Presets.list_presets().items():
        print(f"  - {name}: {desc}")
