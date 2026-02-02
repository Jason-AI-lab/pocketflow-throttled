# Skill 03: Flow-Level Throttling

**Difficulty**: Intermediate
**Source**: `cookbook/rate_limited_llm_batch/flow_throttle_example.py`

## When to Use

- Each item requires **multiple API calls** through a multi-node flow
- Processing many independent items (users, documents, requests)
- Want to limit how many items are processed concurrently
- Need to prevent overwhelming APIs with too many parallel flows

## Key Concepts

`ThrottledAsyncParallelBatchFlow` runs **multiple copies of the entire flow** in parallel, each with different parameters.

**Critical Distinction**:
- **Node throttling** (Skill 01): Limits API calls *within* a node
- **Flow throttling** (Skill 03): Limits how many *complete flows* run at once

## Core Pattern

```python
from pocketflow import AsyncNode
from pocketflow_throttled import ThrottledAsyncParallelBatchFlow

# Define nodes (each flow instance runs these)
class StepA(AsyncNode):
    async def exec_async(self, _):
        item_id = self.params["item_id"]  # Different per flow instance
        return await api_call_1(item_id)

    async def post_async(self, shared, prep_res, exec_res):
        return "step_b"

class StepB(AsyncNode):
    async def exec_async(self, _):
        item_id = self.params["item_id"]
        return await api_call_2(item_id)

# Build the node graph
step_a = StepA()
step_b = StepB()
step_a - "step_b" >> step_b

# Define the throttled flow
class MyThrottledFlow(ThrottledAsyncParallelBatchFlow):
    # Limit concurrent flow instances
    max_concurrent_flows = 5        # Process 5 items at once
    max_flows_per_minute = 60       # Start max 60 items per minute

    async def prep_async(self, shared):
        """Return list of param dicts - one per flow instance."""
        return [
            {"item_id": 1},  # Flow instance 1
            {"item_id": 2},  # Flow instance 2
            {"item_id": 3},  # Flow instance 3
            # ... more items
        ]

# Run
flow = MyThrottledFlow(start=step_a)
await flow.run_async({"data": ...})

# Check stats
print(flow.stats)
# {'max_concurrent_flows': 5, 'completed_flows': 100, ...}
```

## Complete Example: User Processing Pipeline

```python
from pocketflow import AsyncNode
from pocketflow_throttled import ThrottledAsyncParallelBatchFlow

class FetchUserProfileNode(AsyncNode):
    """Fetch user profile from API."""

    async def exec_async(self, _):
        user_id = self.params["user_id"]
        profile = await api.get(f"/users/{user_id}/profile")
        return profile

    async def post_async(self, shared, prep_res, exec_res):
        # Store in shared using unique key (avoid race conditions)
        user_id = self.params["user_id"]
        shared.setdefault("profiles", {})[user_id] = exec_res
        return "fetch_orders"

class FetchUserOrdersNode(AsyncNode):
    """Fetch user orders from API."""

    async def exec_async(self, _):
        user_id = self.params["user_id"]
        orders = await api.get(f"/users/{user_id}/orders")
        return orders

    async def post_async(self, shared, prep_res, exec_res):
        user_id = self.params["user_id"]
        shared.setdefault("orders", {})[user_id] = exec_res
        return "default"

# Build flow graph
profile_node = FetchUserProfileNode()
orders_node = FetchUserOrdersNode()
profile_node - "fetch_orders" >> orders_node

# Define throttled flow
class UserProcessingFlow(ThrottledAsyncParallelBatchFlow):
    """
    Process users with throttled parallelism.

    Each user goes through: fetch_profile → fetch_orders
    Only 5 users are processed concurrently.
    """
    max_concurrent_flows = 5
    max_flows_per_minute = 60

    async def prep_async(self, shared):
        """One flow instance per user."""
        user_ids = shared["user_ids"]
        return [{"user_id": uid} for uid in user_ids]

# Usage
async def process_users():
    flow = UserProcessingFlow(start=profile_node)

    shared = {"user_ids": list(range(100))}  # 100 users

    await flow.run_async(shared)

    # Results are in shared
    print(f"Processed {len(shared['profiles'])} users")
    print(f"Got orders for {len(shared['orders'])} users")

    # Check stats
    print(f"Flow stats: {flow.stats}")
```

## How It Works

### Execution Model

```
prep_async() returns:
[
    {"user_id": 1},
    {"user_id": 2},
    {"user_id": 3},
    ... (100 total)
]

With max_concurrent_flows = 5:

┌─────────────────────────────────────────────────┐
│  Flow Instance 1        Flow Instance 2         │
│  params={user_id:1}     params={user_id:2}      │
│  ┌──────┐               ┌──────┐                │
│  │NodeA │──▶│NodeB│     │NodeA │──▶│NodeB│      │
│  └──────┘   └─────┘     └──────┘   └─────┘      │
├─────────────────────────────────────────────────┤
│  Flow Instance 3        Flow Instance 4         │
│  ... (up to 5 running concurrently)             │
└─────────────────────────────────────────────────┘

Instances 6-100 wait in queue
```

### Parameter Isolation

Each flow instance has **its own `self.params`**:

```python
# Flow instance 1: self.params = {"user_id": 1}
# Flow instance 2: self.params = {"user_id": 2}
# etc.

class MyNode(AsyncNode):
    async def exec_async(self, _):
        # Each instance sees different params
        user_id = self.params["user_id"]
        # Instance 1 sees 1, instance 2 sees 2, etc.
```

### Shared State Safety

**⚠️ CRITICAL**: All flow instances share the same `shared` dict!

```python
# ❌ UNSAFE - Race condition!
class BadNode(AsyncNode):
    async def post_async(self, shared, prep_res, exec_res):
        shared["counter"] += 1  # Multiple flows writing at once!

# ✅ SAFE - Use unique keys
class GoodNode(AsyncNode):
    async def post_async(self, shared, prep_res, exec_res):
        user_id = self.params["user_id"]
        # Each flow writes to different key
        shared.setdefault("results", {})[user_id] = exec_res
```

## Adaptive Flow-Level Throttling

Use `AdaptiveThrottledBatchFlow` for self-tuning flow concurrency:

```python
from pocketflow_throttled import AdaptiveThrottledBatchFlow

class AdaptiveUserFlow(AdaptiveThrottledBatchFlow):
    """Automatically adjusts how many users to process concurrently."""

    initial_concurrent_flows = 10
    min_concurrent_flows = 2
    max_concurrent_flows = 50
    backoff_factor = 0.5
    recovery_threshold = 10
    recovery_factor = 1.3

    async def prep_async(self, shared):
        return [{"user_id": uid} for uid in shared["user_ids"]]

# Starts with 10 concurrent flows
# Backs off to 5 if rate limited
# Recovers to 6-7 after 10 successes
```

## With Presets

```python
from pocketflow_throttled import ThrottledAsyncParallelBatchFlow, FlowPresets

class PresetFlow(ThrottledAsyncParallelBatchFlow):
    # Use pre-configured settings
    max_concurrent_flows = FlowPresets.MODERATE["max_concurrent_flows"]
    max_flows_per_minute = FlowPresets.MODERATE["max_flows_per_minute"]

# Or pass as kwargs
flow = ThrottledAsyncParallelBatchFlow(
    start=my_node,
    **FlowPresets.BATCH_PROCESSING
)
```

## Available Flow Presets

```python
from pocketflow_throttled import FlowPresets

# Generic presets
FlowPresets.CONSERVATIVE      # 5 flows, 30/min
FlowPresets.MODERATE          # 10 flows, 60/min
FlowPresets.AGGRESSIVE        # 20 flows, 120/min

# Use-case specific
FlowPresets.BATCH_PROCESSING  # 15 flows, 100/min
FlowPresets.DATA_PIPELINE     # 10 flows, 50/min
FlowPresets.REALTIME          # 5 flows, 300/min
FlowPresets.HEAVY_PROCESSING  # 3 flows, 20/min

# Adaptive presets
FlowPresets.ADAPTIVE_CONSERVATIVE
FlowPresets.ADAPTIVE_MODERATE
FlowPresets.ADAPTIVE_AGGRESSIVE
```

## Monitoring Flow Execution

```python
flow = MyThrottledFlow(start=node)
await flow.run_async(shared)

stats = flow.stats
print(f"Max concurrent flows: {stats['max_concurrent_flows']}")
print(f"Completed flows: {stats['completed_flows']}")
print(f"Failed flows: {stats['failed_flows']}")

# For adaptive flows
if hasattr(flow, 'current_concurrent_flows'):
    print(f"Current concurrent: {stats['current_concurrent_flows']}")
    print(f"Rate limits hit: {stats['total_rate_limits']}")
```

## Common Patterns

### Pattern: Document Processing
```python
# Each document goes through: analyze → summarize → store
class DocumentFlow(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = 10  # Process 10 docs at once

    async def prep_async(self, shared):
        return [
            {"doc_id": doc.id, "content": doc.content}
            for doc in shared["documents"]
        ]
```

### Pattern: Multi-Region Requests
```python
# Process requests across different regions
class MultiRegionFlow(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = 5

    async def prep_async(self, shared):
        return [
            {"region": "us", "request_id": rid}
            for rid in shared["us_requests"]
        ] + [
            {"region": "eu", "request_id": rid}
            for rid in shared["eu_requests"]
        ]
```

### Pattern: User Onboarding Pipeline
```python
# Each user: create_account → send_email → setup_preferences
class OnboardingFlow(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = 3  # Don't overwhelm email service

    async def prep_async(self, shared):
        return [
            {
                "email": user.email,
                "name": user.name,
                "preferences": user.preferences
            }
            for user in shared["new_users"]
        ]
```

## Performance Comparison

For 100 items, each requiring 2 sequential API calls (0.5s each):

| Approach | Time | Notes |
|----------|------|-------|
| Sequential (no flow throttle) | ~100s | One at a time |
| **Flow throttled (5 concurrent)** | **~20s** | 5 flows × 2 calls × 0.5s |
| **Flow throttled (10 concurrent)** | **~10s** | Optimal for many APIs |
| No throttle | ~1s | ❌ 100+ 429 errors |

## Decision: Node vs Flow Throttling

Use **Node throttling** when:
- Single node processing items
- Items are independent
- Node makes multiple API calls per item

Use **Flow throttling** when:
- Multi-node pipeline per item
- Each item goes through several steps
- Want to limit total concurrent items

Use **Both** (nested) when:
- Multi-node pipeline
- Each node makes multiple API calls
- See [Skill 07: Nested Throttling](07-nested-throttling.md)

## Resetting Between Runs

```python
flow = MyThrottledFlow(start=node)

# First batch
await flow.run_async({"items": batch1})

# Reset limiter before second batch
flow.reset_limiter()

# Second batch
await flow.run_async({"items": batch2})
```

## Related Skills

- **Simpler**: [Skill 01: Basic Node Throttling](01-basic-node-throttling.md) - Single-node batches
- **Parameters**: [Skill 05: Parameterized Flows](05-parameterized-flows.md) - How params work
- **Advanced**: [Skill 07: Nested Throttling](07-nested-throttling.md) - Combine flow + node
- **Adaptive**: [Skill 02: Adaptive Throttling](02-adaptive-throttling.md) - Self-tuning flows

## When NOT to Use

- **Single-node batch** → Use [Node Throttling](01-basic-node-throttling.md)
- **Sequential processing required** → Use `AsyncBatchFlow` (no throttling needed)
- **Shared state between items** → Redesign for independence or use node throttling
