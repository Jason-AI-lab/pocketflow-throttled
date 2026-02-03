"""
Throttled Flow Example
======================

This example demonstrates ThrottledAsyncParallelBatchFlow, which limits
how many flow instances run concurrently when processing batches.

Use Case:
    Processing many items (users, documents, etc.) where each item
    requires multiple API calls through a multi-node flow.

Key Concepts:
    - ThrottledAsyncParallelBatchFlow: Limits concurrent flow instances
    - Each flow instance runs the entire node graph with different params
    - Prevents overwhelming APIs when batch processing at scale

Usage:
    python flow_throttle_example.py
"""

import asyncio
import random
import time
from typing import Dict, Any

from pocketflow import AsyncNode, AsyncFlow

from pocketflow_throttled import (
    ThrottledAsyncParallelBatchFlow,
    ThrottledParallelBatchNode,
    FlowPresets,
)


# =============================================================================
# Simulated API
# =============================================================================

class SimulatedAPI:
    """Simulates an external API with rate limits."""
    
    def __init__(self):
        self.call_count = 0
        self.concurrent = 0
        self.max_concurrent_seen = 0
    
    async def call(self, endpoint: str) -> Dict[str, Any]:
        """Simulate an API call."""
        self.call_count += 1
        self.concurrent += 1
        self.max_concurrent_seen = max(self.max_concurrent_seen, self.concurrent)
        
        # Simulate network latency
        await asyncio.sleep(random.uniform(0.05, 0.15))
        
        self.concurrent -= 1
        return {"endpoint": endpoint, "status": "success"}


api = SimulatedAPI()


# =============================================================================
# Example 1: Basic Flow Throttling
# =============================================================================

class FetchUserProfileNode(AsyncNode):
    """Fetch user profile from API."""
    
    async def exec_async(self, _):
        user_id = self.params["user_id"]
        result = await api.call(f"/users/{user_id}/profile")
        return {"user_id": user_id, "profile": result}
    
    async def post_async(self, shared, prep_res, exec_res):
        shared.setdefault("profiles", {})[exec_res["user_id"]] = exec_res["profile"]
        return "fetch_orders"


class FetchUserOrdersNode(AsyncNode):
    """Fetch user orders from API."""
    
    async def exec_async(self, _):
        user_id = self.params["user_id"]
        result = await api.call(f"/users/{user_id}/orders")
        return {"user_id": user_id, "orders": result}
    
    async def post_async(self, shared, prep_res, exec_res):
        shared.setdefault("orders", {})[exec_res["user_id"]] = exec_res["orders"]
        return "default"


class BasicUserFlow(ThrottledAsyncParallelBatchFlow):
    """
    Process users with throttled parallelism.
    
    Only 5 users are processed concurrently, even if we have hundreds.
    """
    max_concurrent_flows = 5
    max_flows_per_minute = 60
    
    async def prep_async(self, shared):
        return [{"user_id": uid} for uid in shared["user_ids"]]


async def demo_basic_throttling():
    """Demonstrate basic flow throttling."""
    print("=" * 60)
    print("Example 1: Basic Flow Throttling")
    print("=" * 60)
    
    # Build flow: profile -> orders
    profile_node = FetchUserProfileNode()
    orders_node = FetchUserOrdersNode()
    profile_node - "fetch_orders" >> orders_node
    
    flow = BasicUserFlow(start=profile_node)
    
    # Process 20 users with throttling
    shared = {"user_ids": list(range(20))}
    
    api.call_count = 0
    api.max_concurrent_seen = 0
    start = time.time()
    
    await flow.run_async(shared)
    
    elapsed = time.time() - start
    
    print(f"\nResults:")
    print(f"  - Users processed: {len(shared.get('profiles', {}))}")
    print(f"  - Total API calls: {api.call_count}")
    print(f"  - Max concurrent API calls: {api.max_concurrent_seen}")
    print(f"  - Time elapsed: {elapsed:.2f}s")
    print(f"  - Flow stats: {flow.stats}")


# =============================================================================
# Example 2: Nested Throttling (Flow + Node)
# =============================================================================

class FetchUserDataNode(ThrottledParallelBatchNode):
    """
    Fetch multiple data points per user with node-level throttling.
    
    This node has its own rate limiting for API calls within a single user.
    """
    max_concurrent = 3  # 3 concurrent API calls per user
    
    async def prep_async(self, shared):
        user_id = self.params["user_id"]
        # Each user needs multiple API calls
        return [
            f"/users/{user_id}/profile",
            f"/users/{user_id}/orders",
            f"/users/{user_id}/preferences",
            f"/users/{user_id}/notifications",
        ]
    
    async def exec_async(self, endpoint):
        return await api.call(endpoint)
    
    async def post_async(self, shared, prep_res, exec_res_list):
        user_id = self.params["user_id"]
        shared.setdefault("user_data", {})[user_id] = exec_res_list
        return "default"


class NestedThrottledFlow(ThrottledAsyncParallelBatchFlow):
    """
    Process users with both flow-level and node-level throttling.
    
    - Flow level: Max 5 users concurrently
    - Node level: Max 3 API calls per user concurrently
    - Total max concurrent API calls: 5 × 3 = 15
    """
    max_concurrent_flows = 5
    
    async def prep_async(self, shared):
        return [{"user_id": uid} for uid in shared["user_ids"]]


async def demo_nested_throttling():
    """Demonstrate nested throttling (flow + node)."""
    print("\n" + "=" * 60)
    print("Example 2: Nested Throttling (Flow + Node)")
    print("=" * 60)
    
    flow = NestedThrottledFlow(start=FetchUserDataNode())
    
    shared = {"user_ids": list(range(15))}
    
    api.call_count = 0
    api.max_concurrent_seen = 0
    start = time.time()
    
    await flow.run_async(shared)
    
    elapsed = time.time() - start
    
    print(f"\nResults:")
    print(f"  - Users processed: {len(shared.get('user_data', {}))}")
    print(f"  - Total API calls: {api.call_count}")
    print(f"  - Max concurrent API calls: {api.max_concurrent_seen}")
    print(f"  - Expected max (5 flows × 3 calls): 15")
    print(f"  - Time elapsed: {elapsed:.2f}s")
    print(f"  - Flow stats: {flow.stats}")


# =============================================================================
# Example 3: Using Flow Presets
# =============================================================================

async def demo_flow_presets():
    """Demonstrate using flow presets."""
    print("\n" + "=" * 60)
    print("Example 3: Using Flow Presets")
    print("=" * 60)
    
    print("\nAvailable Flow Presets:")
    for name, desc in FlowPresets.list_presets().items():
        print(f"  - {name}: {desc}")
    
    print("\nPreset configurations:")
    print(f"  CONSERVATIVE: {FlowPresets.CONSERVATIVE}")
    print(f"  MODERATE: {FlowPresets.MODERATE}")
    print(f"  AGGRESSIVE: {FlowPresets.AGGRESSIVE}")
    print(f"  BATCH_PROCESSING: {FlowPresets.BATCH_PROCESSING}")
    
    # Using preset via kwargs
    class PresetFlow(ThrottledAsyncParallelBatchFlow):
        async def prep_async(self, shared):
            return [{"id": i} for i in range(10)]
    
    # Pass preset as kwargs
    flow = PresetFlow(
        start=FetchUserProfileNode(),
        **FlowPresets.MODERATE
    )
    
    print(f"\nCreated flow with MODERATE preset:")
    print(f"  max_concurrent_flows: {flow.max_concurrent_flows}")
    print(f"  max_flows_per_minute: {flow.max_flows_per_minute}")


# =============================================================================
# Main
# =============================================================================

async def main():
    """Run all examples."""
    await demo_basic_throttling()
    await demo_nested_throttling()
    await demo_flow_presets()
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("""
Key Takeaways:

1. ThrottledAsyncParallelBatchFlow limits concurrent flow instances
   - Each flow instance runs the entire node graph
   - Useful for batch processing (users, documents, etc.)

2. Nested throttling combines flow + node limits
   - Flow level: controls how many items processed in parallel
   - Node level: controls API calls within each item
   - Total limit is the product: flows × calls_per_flow

3. FlowPresets provide ready-to-use configurations
   - CONSERVATIVE, MODERATE, AGGRESSIVE for general use
   - BATCH_PROCESSING, DATA_PIPELINE for specific workloads
   - ADAPTIVE_* presets for AdaptiveThrottledBatchFlow
""")


if __name__ == "__main__":
    asyncio.run(main())
