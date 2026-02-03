"""
Shared Rate Limiter Example
===========================

This example demonstrates using LimiterRegistry to share rate limiters
across multiple nodes and flows for global API coordination.

Use Case:
    When multiple independent nodes/flows call the same API, you need
    to coordinate their rate limiting to avoid exceeding global limits.

Key Concepts:
    - LimiterRegistry: Global registry for shared rate limiters
    - Shared limiters ensure total API calls stay within limits
    - Works across different nodes, flows, and even processes (with caveats)

Usage:
    python shared_limiter_example.py
"""

import asyncio
import random
import time
from typing import Dict, Any

from pocketflow import AsyncNode, AsyncFlow

from pocketflow_throttled import (
    LimiterRegistry,
    ThrottledAsyncParallelBatchFlow,
)


# =============================================================================
# Simulated API
# =============================================================================

class APITracker:
    """Tracks API call statistics."""
    
    def __init__(self):
        self.call_count = 0
        self.concurrent = 0
        self.max_concurrent = 0
        self.calls_by_endpoint = {}
    
    async def call(self, endpoint: str) -> Dict[str, Any]:
        """Simulate an API call."""
        self.call_count += 1
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        self.calls_by_endpoint[endpoint] = self.calls_by_endpoint.get(endpoint, 0) + 1
        
        await asyncio.sleep(random.uniform(0.05, 0.1))
        
        self.concurrent -= 1
        return {"endpoint": endpoint, "status": "ok"}
    
    def reset(self):
        self.call_count = 0
        self.concurrent = 0
        self.max_concurrent = 0
        self.calls_by_endpoint = {}


api = APITracker()


# =============================================================================
# Example 1: Multiple Nodes Sharing a Limiter
# =============================================================================

class ProfileFetchNode(AsyncNode):
    """Fetch user profiles using shared limiter."""
    
    async def exec_async(self, _):
        user_id = self.params["user_id"]
        
        # Use the shared limiter
        async with LimiterRegistry.get("main_api"):
            result = await api.call(f"/profiles/{user_id}")
        
        return result
    
    async def post_async(self, shared, prep_res, exec_res):
        shared.setdefault("profiles", []).append(exec_res)
        return "default"


class OrderFetchNode(AsyncNode):
    """Fetch orders using the SAME shared limiter."""
    
    async def exec_async(self, _):
        user_id = self.params["user_id"]
        
        # Uses the same limiter as ProfileFetchNode
        async with LimiterRegistry.get("main_api"):
            result = await api.call(f"/orders/{user_id}")
        
        return result
    
    async def post_async(self, shared, prep_res, exec_res):
        shared.setdefault("orders", []).append(exec_res)
        return "default"


async def demo_shared_limiter():
    """Demonstrate multiple nodes sharing a limiter."""
    print("=" * 60)
    print("Example 1: Multiple Nodes Sharing a Limiter")
    print("=" * 60)
    
    # Reset for clean test
    LimiterRegistry.reset()
    api.reset()
    
    # Register the shared limiter ONCE at startup
    # Both nodes will share this 5-concurrent limit
    LimiterRegistry.register(
        "main_api",
        max_concurrent=5,
        max_per_window=100,
        window_seconds=60.0
    )
    
    print(f"\nRegistered shared limiter 'main_api':")
    print(f"  {LimiterRegistry.list_all()['main_api']}")
    
    # Create flows that use nodes with shared limiters
    class ProfileFlow(ThrottledAsyncParallelBatchFlow):
        max_concurrent_flows = 20  # High flow concurrency
        
        async def prep_async(self, shared):
            return [{"user_id": i} for i in range(15)]
    
    class OrderFlow(ThrottledAsyncParallelBatchFlow):
        max_concurrent_flows = 20  # High flow concurrency
        
        async def prep_async(self, shared):
            return [{"user_id": i} for i in range(15)]
    
    profile_flow = ProfileFlow(start=ProfileFetchNode())
    order_flow = OrderFlow(start=OrderFetchNode())
    
    # Run both flows concurrently
    start = time.time()
    await asyncio.gather(
        profile_flow.run_async({}),
        order_flow.run_async({})
    )
    elapsed = time.time() - start
    
    print(f"\nResults (both flows ran concurrently):")
    print(f"  - Total API calls: {api.call_count}")
    print(f"  - Max concurrent API calls: {api.max_concurrent}")
    print(f"  - Shared limit was: 5")
    print(f"  - Calls by endpoint: {api.calls_by_endpoint}")
    print(f"  - Time elapsed: {elapsed:.2f}s")
    
    # The shared limiter ensured total concurrent calls never exceeded 5
    # even though we had 40 potential concurrent flows (20 + 20)


# =============================================================================
# Example 2: Multiple APIs with Different Limits
# =============================================================================

class OpenAINode(AsyncNode):
    """Simulates calls to OpenAI API."""
    
    async def exec_async(self, _):
        async with LimiterRegistry.get("openai"):
            result = await api.call("/openai/completions")
        return result


class AnthropicNode(AsyncNode):
    """Simulates calls to Anthropic API."""
    
    async def exec_async(self, _):
        async with LimiterRegistry.get("anthropic"):
            result = await api.call("/anthropic/messages")
        return result


async def demo_multiple_apis():
    """Demonstrate multiple APIs with different limits."""
    print("\n" + "=" * 60)
    print("Example 2: Multiple APIs with Different Limits")
    print("=" * 60)
    
    # Reset
    LimiterRegistry.reset()
    api.reset()
    
    # Register different limits for different APIs
    LimiterRegistry.register("openai", max_concurrent=5, max_per_window=60)
    LimiterRegistry.register("anthropic", max_concurrent=3, max_per_window=30)
    
    print("\nRegistered limiters:")
    for name, config in LimiterRegistry.list_all().items():
        print(f"  - {name}: {config}")
    
    # Simulate concurrent usage
    async def call_openai():
        async with LimiterRegistry.get("openai"):
            await api.call("/openai")
    
    async def call_anthropic():
        async with LimiterRegistry.get("anthropic"):
            await api.call("/anthropic")
    
    start = time.time()
    await asyncio.gather(
        *[call_openai() for _ in range(20)],
        *[call_anthropic() for _ in range(15)]
    )
    elapsed = time.time() - start
    
    print(f"\nResults:")
    print(f"  - Total API calls: {api.call_count}")
    print(f"  - OpenAI limit: 5, Anthropic limit: 3")
    print(f"  - Max concurrent seen: {api.max_concurrent} (could be up to 8)")
    print(f"  - Time elapsed: {elapsed:.2f}s")


# =============================================================================
# Example 3: Lazy Registration with get_or_create
# =============================================================================

class LazyNode(AsyncNode):
    """Node that lazily creates its limiter if needed."""
    
    async def exec_async(self, _):
        # get_or_create ensures the limiter exists without knowing
        # if it was pre-registered
        limiter = LimiterRegistry.get_or_create(
            "lazy_api",
            max_concurrent=10,
            max_per_window=100
        )
        
        async with limiter:
            result = await api.call("/lazy")
        
        return result


async def demo_lazy_registration():
    """Demonstrate lazy limiter registration."""
    print("\n" + "=" * 60)
    print("Example 3: Lazy Registration with get_or_create")
    print("=" * 60)
    
    LimiterRegistry.reset()
    api.reset()
    
    print("\nBefore: No limiters registered")
    print(f"  Registered: {LimiterRegistry.list_names()}")
    
    # First node call creates the limiter
    node = LazyNode()
    node.params = {}
    await node.exec_async(None)
    
    print("\nAfter first call: Limiter created")
    print(f"  Registered: {LimiterRegistry.list_names()}")
    print(f"  Config: {LimiterRegistry.list_all()['lazy_api']}")
    
    # Subsequent calls reuse the same limiter
    await asyncio.gather(*[node.exec_async(None) for _ in range(5)])
    
    print(f"\nAfter 5 more calls: Same limiter reused")
    print(f"  Total calls: {api.call_count}")


# =============================================================================
# Example 4: Monitoring Limiter Stats
# =============================================================================

async def demo_monitoring():
    """Demonstrate monitoring limiter statistics."""
    print("\n" + "=" * 60)
    print("Example 4: Monitoring Limiter Stats")
    print("=" * 60)
    
    LimiterRegistry.reset()
    
    # Register a limiter
    LimiterRegistry.register(
        "monitored_api",
        max_concurrent=3,
        max_per_window=10,
        window_seconds=5.0  # Short window for demo
    )
    
    async def make_calls():
        """Make some calls to populate stats."""
        for i in range(8):
            async with LimiterRegistry.get("monitored_api"):
                await asyncio.sleep(0.1)
            
            # Check stats after each call
            stats = LimiterRegistry.stats("monitored_api")
            print(f"  Call {i+1}: window_count={stats['current_window_count']}")
    
    print("\nMaking 8 calls with monitoring:")
    await make_calls()
    
    print(f"\nFinal stats: {LimiterRegistry.stats('monitored_api')}")


# =============================================================================
# Main
# =============================================================================

async def main():
    """Run all examples."""
    await demo_shared_limiter()
    await demo_multiple_apis()
    await demo_lazy_registration()
    await demo_monitoring()
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("""
Key Takeaways:

1. LimiterRegistry provides global rate limiter coordination
   - Register limiters once at app startup
   - Access them by name from anywhere

2. Multiple nodes/flows can share the same limiter
   - Total concurrent calls across all users of the limiter
   - Prevents exceeding API limits even with parallel flows

3. get_or_create enables lazy registration
   - Nodes can ensure a limiter exists without pre-configuration
   - Useful for libraries or reusable components

4. Stats monitoring helps with debugging
   - Track current window usage
   - Identify bottlenecks

Best Practices:
   - Register shared limiters at application startup
   - Use descriptive names: "openai", "anthropic", "internal_api"
   - Set limits conservatively, then increase as needed
   - Use get_or_create for optional/configurable components
""")


if __name__ == "__main__":
    asyncio.run(main())
