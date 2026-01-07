"""
Adaptive Throttling Example
===========================

This example demonstrates AdaptiveThrottledNode, which automatically
adjusts its throughput based on API responses.

Key features:
- Starts at an initial concurrency level
- Backs off (reduces concurrency) when hitting rate limits
- Gradually recovers throughput after sustained success
- Self-tunes to optimal performance

Usage:
    python adaptive_example.py
"""

import asyncio
import random
import time

from pocketflow import AsyncFlow

from pocketflow_throttled import AdaptiveThrottledNode


# =============================================================================
# Simulated API with Unpredictable Rate Limits
# =============================================================================

class UnpredictableAPI:
    """
    Simulates an API with dynamic rate limits.
    
    The API becomes more restrictive under high load,
    similar to real-world behavior.
    """
    
    def __init__(self):
        self.call_count = 0
        self.calls_this_second = 0
        self.last_second = 0
        self.rate_limit_threshold = 10  # Calls per second before limiting
    
    async def call(self, data: str) -> str:
        """Simulate an API call with dynamic rate limiting."""
        self.call_count += 1
        current_second = int(time.time())
        
        # Reset counter each second
        if current_second != self.last_second:
            self.calls_this_second = 0
            self.last_second = current_second
        
        self.calls_this_second += 1
        
        # Simulate rate limiting under high load
        if self.calls_this_second > self.rate_limit_threshold:
            # Higher chance of rate limit as we exceed threshold
            if random.random() < 0.7:
                raise Exception("429 Too Many Requests")
        
        # Simulate API latency
        await asyncio.sleep(random.uniform(0.05, 0.15))
        
        return f"Processed: {data}"


# Global API instance
api = UnpredictableAPI()


# =============================================================================
# Adaptive Processing Node
# =============================================================================

class AdaptiveProcessingNode(AdaptiveThrottledNode):
    """
    Process items with adaptive rate limiting.
    
    Configuration:
    - Starts with 10 concurrent requests
    - Backs off to minimum of 2 when rate limited
    - Caps at maximum of 30 concurrent
    - Recovers after 5 consecutive successes
    """
    
    # Adaptive throttling configuration
    initial_concurrent = 10
    min_concurrent = 2
    max_concurrent = 30
    backoff_factor = 0.5      # Halve on rate limit
    recovery_threshold = 5     # Recover after 5 successes
    recovery_factor = 1.5     # Increase by 50%
    
    # Also set a per-minute limit as a safety net
    max_per_minute = 300
    
    async def prep_async(self, shared):
        return shared.get("items", [])
    
    async def exec_async(self, item):
        return await api.call(str(item))
    
    async def post_async(self, shared, prep_res, exec_res_list):
        shared["results"] = exec_res_list
        return "default"


# =============================================================================
# Demo: Watch Adaptive Behavior
# =============================================================================

async def demo_adaptive_throttling():
    """
    Demonstrate adaptive throttling behavior.
    
    Shows how the node automatically adjusts concurrency
    based on API responses.
    """
    print("=" * 60)
    print("Adaptive Throttling Demo")
    print("=" * 60)
    
    # Create node
    node = AdaptiveProcessingNode()
    
    print("\nInitial Configuration:")
    print(f"  - Initial concurrent: {node.initial_concurrent}")
    print(f"  - Min concurrent: {node.min_concurrent}")
    print(f"  - Max concurrent: {node.max_concurrent}")
    print(f"  - Backoff factor: {node.backoff_factor}")
    print(f"  - Recovery threshold: {node.recovery_threshold}")
    print(f"  - Recovery factor: {node.recovery_factor}")
    
    # Process items in batches to observe adaptation
    print("\n" + "-" * 40)
    print("Processing batches (watch concurrency adapt):")
    print("-" * 40)
    
    batch_size = 50
    num_batches = 5
    
    for batch_num in range(num_batches):
        items = list(range(batch_num * batch_size, (batch_num + 1) * batch_size))
        shared = {"items": items}
        
        start = time.time()
        await node._run_async(shared)
        elapsed = time.time() - start
        
        stats = node.stats
        print(f"\nBatch {batch_num + 1}:")
        print(f"  - Items processed: {len(items)}")
        print(f"  - Time: {elapsed:.2f}s")
        print(f"  - Current concurrent: {stats['current_concurrent']}")
        print(f"  - Total successes: {stats['total_successes']}")
        print(f"  - Total rate limits: {stats['total_rate_limits']}")
        print(f"  - Consecutive successes: {stats['consecutive_successes']}")
    
    print("\n" + "-" * 40)
    print("Final Statistics:")
    print("-" * 40)
    stats = node.stats
    print(f"  - Final concurrent level: {stats['current_concurrent']}")
    print(f"  - Total API calls succeeded: {stats['total_successes']}")
    print(f"  - Total rate limits hit: {stats['total_rate_limits']}")
    print(f"  - API call count: {api.call_count}")
    
    # Show adaptation behavior
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("""
The AdaptiveThrottledNode automatically:

1. BACKS OFF when hitting rate limits:
   - Detected 429 errors → Reduced concurrency by 50%
   - Reset consecutive success counter
   
2. RECOVERS after sustained success:
   - After 5 consecutive successes → Increased concurrency by 50%
   - Gradually reaches optimal throughput

3. SELF-TUNES to the API's actual limits:
   - No need to know exact rate limits beforehand
   - Adapts to varying conditions
""")


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    asyncio.run(demo_adaptive_throttling())
