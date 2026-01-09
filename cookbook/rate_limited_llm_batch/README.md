# Rate-Limited LLM Batch Processing

This cookbook demonstrates how to use `pocketflow-throttled` for batch processing
with LLM APIs while respecting rate limits.

## Problem

When processing large batches of data with LLM APIs:
- **Without throttling**: Requests fire simultaneously, triggering 429 errors
- **Sequential processing**: Works but is painfully slow
- **Manual rate limiting**: Complex and error-prone

## Solution

`pocketflow-throttled` provides throttling at two levels:
- **Node-level**: `ThrottledParallelBatchNode` limits concurrent API calls within a node
- **Flow-level**: `ThrottledAsyncParallelBatchFlow` limits concurrent flow instances

Both support fixed and adaptive throttling modes.

---

## Node-Level Throttling

### Basic Node Throttling

```python
from pocketflow_throttled import ThrottledParallelBatchNode

class TranslateNode(ThrottledParallelBatchNode):
    max_concurrent = 5      # Max 5 simultaneous API calls
    max_per_minute = 60     # Max 60 calls per minute
    
    async def prep_async(self, shared):
        return shared["texts"]
    
    async def exec_async(self, text):
        return await call_llm(f"Translate: {text}")
    
    async def post_async(self, shared, prep_res, exec_res_list):
        shared["translations"] = exec_res_list
        return "default"
```

### Adaptive Node Throttling

```python
from pocketflow_throttled import AdaptiveThrottledNode

class SmartTranslateNode(AdaptiveThrottledNode):
    initial_concurrent = 10  # Start optimistic
    min_concurrent = 2       # Never go below 2
    max_concurrent = 50      # Cap at 50
    backoff_factor = 0.5     # Halve on rate limit
    recovery_threshold = 10  # Successes before recovery
    recovery_factor = 1.2    # +20% after sustained success
    
    async def exec_async(self, text):
        return await call_llm(text)
```

---

## Flow-Level Throttling

Use flow-level throttling when each item in your batch requires **multiple API calls** through a multi-node flow.

### Basic Flow Throttling (`flow_throttle_example.py`)

```python
from pocketflow import AsyncNode
from pocketflow_throttled import ThrottledAsyncParallelBatchFlow

class FetchUserNode(AsyncNode):
    async def exec_async(self, _):
        user_id = self.params["user_id"]
        return await fetch_user_data(user_id)
    
    async def post_async(self, shared, prep_res, exec_res):
        shared.setdefault("users", {})[self.params["user_id"]] = exec_res
        return "process"

class ProcessUserNode(AsyncNode):
    async def exec_async(self, _):
        user_id = self.params["user_id"]
        return await process_with_llm(user_id)

# Build flow: fetch -> process
fetch = FetchUserNode()
process = ProcessUserNode()
fetch - "process" >> process

class UserProcessingFlow(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = 10      # Process 10 users concurrently
    max_flows_per_minute = 60      # Start max 60 users per minute
    
    async def prep_async(self, shared):
        # Return list of param dicts - one flow instance per user
        return [{"user_id": uid} for uid in shared["user_ids"]]

# Process 1000 users, 10 at a time
flow = UserProcessingFlow(start=fetch)
await flow.run_async({"user_ids": range(1000)})

print(flow.stats)
# {'max_concurrent_flows': 10, 'completed_flows': 1000, 'failed_flows': 0, ...}
```

### Adaptive Flow Throttling

```python
from pocketflow_throttled import AdaptiveThrottledBatchFlow, RateLimitHit

class APINode(AsyncNode):
    async def exec_async(self, _):
        try:
            return await call_flaky_api()
        except TooManyRequestsError:
            # Signal rate limit to parent flow
            raise RateLimitHit("API rate limit exceeded")

class SmartUserFlow(AdaptiveThrottledBatchFlow):
    initial_concurrent_flows = 20   # Start aggressive
    min_concurrent_flows = 2        # Don't go below 2
    max_concurrent_flows = 50       # Cap at 50
    backoff_factor = 0.5            # Halve on rate limit
    recovery_threshold = 15         # 15 successes to recover
    recovery_factor = 1.3           # +30% on recovery
    
    async def prep_async(self, shared):
        return [{"user_id": uid} for uid in shared["user_ids"]]

flow = SmartUserFlow(start=APINode())
await flow.run_async({"user_ids": range(500)})

print(flow.stats)
# {'current_concurrent_flows': 12, 'total_rate_limits': 3, ...}
```

### Nested Throttling (Flow + Node)

Combine flow-level and node-level throttling for fine-grained control:

```python
from pocketflow_throttled import (
    ThrottledAsyncParallelBatchFlow,
    ThrottledParallelBatchNode,
)

class FetchUserDataNode(ThrottledParallelBatchNode):
    """Each user needs multiple API calls - throttle at node level."""
    max_concurrent = 3      # 3 API calls per user at once
    max_per_minute = 30     # 30 calls per minute per user
    
    async def prep_async(self, shared):
        user_id = self.params["user_id"]
        return [
            f"/users/{user_id}/profile",
            f"/users/{user_id}/orders",
            f"/users/{user_id}/preferences",
        ]
    
    async def exec_async(self, endpoint):
        return await call_api(endpoint)

class UserBatchFlow(ThrottledAsyncParallelBatchFlow):
    """Process many users - throttle at flow level."""
    max_concurrent_flows = 5    # 5 users at once
    
    async def prep_async(self, shared):
        return [{"user_id": uid} for uid in shared["user_ids"]]

# Effective limits:
# - Max 5 users processed concurrently
# - Each user makes max 3 concurrent API calls
# - Total max concurrent API calls: 5 × 3 = 15

flow = UserBatchFlow(start=FetchUserDataNode())
await flow.run_async({"user_ids": range(100)})
```

---

## Shared Rate Limiters (`shared_limiter_example.py`)

Use `LimiterRegistry` when multiple nodes/flows need to share the same global rate limit.

### Basic Shared Limiter

```python
from pocketflow_throttled import LimiterRegistry

# Register at app startup (once)
LimiterRegistry.register(
    "openai",
    max_concurrent=10,
    max_per_window=60,
    window_seconds=60.0
)

# Use anywhere in your code
class Node1(AsyncNode):
    async def exec_async(self, item):
        async with LimiterRegistry.get("openai"):
            return await call_openai(item)

class Node2(AsyncNode):
    async def exec_async(self, item):
        # Same limiter - total concurrent calls across both nodes <= 10
        async with LimiterRegistry.get("openai"):
            return await call_openai(item)
```

### Multiple APIs with Different Limits

```python
# Register different limits for different APIs
LimiterRegistry.register("openai", max_concurrent=10, max_per_window=60)
LimiterRegistry.register("anthropic", max_concurrent=5, max_per_window=50)
LimiterRegistry.register("internal_api", max_concurrent=20, max_per_window=None)

class MultiAPINode(AsyncNode):
    async def exec_async(self, item):
        # Each API has its own independent limit
        async with LimiterRegistry.get("openai"):
            openai_result = await call_openai(item)
        
        async with LimiterRegistry.get("anthropic"):
            anthropic_result = await call_anthropic(item)
        
        return {"openai": openai_result, "anthropic": anthropic_result}
```

### Lazy Registration

```python
class FlexibleNode(AsyncNode):
    async def exec_async(self, item):
        # Creates limiter if not exists, reuses if exists
        limiter = LimiterRegistry.get_or_create(
            "my_api",
            max_concurrent=10,
            max_per_window=100
        )
        
        async with limiter:
            return await call_api(item)
```

---

## Using Presets

### Node Presets

```python
from pocketflow_throttled import ThrottledParallelBatchNode, Presets

# Use pre-configured limits
class MyNode(ThrottledParallelBatchNode):
    max_concurrent = Presets.OPENAI_TIER1["max_concurrent"]
    max_per_minute = Presets.OPENAI_TIER1["max_per_minute"]

# Or pass as kwargs
node = ThrottledParallelBatchNode(**Presets.ANTHROPIC_STANDARD)
```

Available node presets:
- **OpenAI**: `OPENAI_FREE`, `OPENAI_TIER1` through `OPENAI_TIER5`
- **Anthropic**: `ANTHROPIC_FREE`, `ANTHROPIC_BUILD_TIER1` through `ANTHROPIC_BUILD_TIER4`
- **Google**: `GOOGLE_FREE`, `GOOGLE_PAY_AS_YOU_GO`
- **Generic**: `CONSERVATIVE`, `MODERATE`, `AGGRESSIVE`

### Flow Presets

```python
from pocketflow_throttled import ThrottledAsyncParallelBatchFlow, FlowPresets

class MyFlow(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = FlowPresets.MODERATE["max_concurrent_flows"]
    max_flows_per_minute = FlowPresets.MODERATE["max_flows_per_minute"]

# Or pass as kwargs
flow = ThrottledAsyncParallelBatchFlow(start=node, **FlowPresets.BATCH_PROCESSING)
```

Available flow presets:
- **Generic**: `CONSERVATIVE`, `MODERATE`, `AGGRESSIVE`, `HIGH_THROUGHPUT`
- **Use-case**: `BATCH_PROCESSING`, `DATA_PIPELINE`, `REALTIME`, `HEAVY_PROCESSING`
- **Adaptive**: `ADAPTIVE_CONSERVATIVE`, `ADAPTIVE_MODERATE`, `ADAPTIVE_AGGRESSIVE`

---

## Signaling Rate Limits

### From Node to Flow

Use `RateLimitHit` to signal rate limits from nodes to adaptive flows:

```python
from pocketflow_throttled import AdaptiveThrottledBatchFlow, RateLimitHit

class MyNode(AsyncNode):
    async def exec_async(self, item):
        try:
            return await call_api(item)
        except APIRateLimitError as e:
            # Signal to parent flow for flow-level adaptation
            raise RateLimitHit(
                message="API rate limit exceeded",
                retry_after=e.retry_after,  # Optional hint
                source="my_api"             # Optional identifier
            )
```

### Auto-Propagate from Adaptive Nodes

```python
from pocketflow_throttled import AdaptiveThrottledNode

class AutoSignalNode(AdaptiveThrottledNode):
    propagate_rate_limit = True  # Auto-raise RateLimitHit on detection
    
    async def exec_async(self, item):
        # If this hits a rate limit, it will:
        # 1. Back off internally (node-level adaptation)
        # 2. Raise RateLimitHit for parent flow (flow-level adaptation)
        return await call_api(item)
```

---

## Performance Comparison

| Approach | 100 Items | Rate Limit Errors | Use Case |
|----------|-----------|-------------------|----------|
| Sequential | ~100s | None | Simple, low volume |
| Parallel (no throttle) | ~10s | Many 429s | ❌ Don't use |
| **Node Throttled** | ~20s | None | Single-node batches |
| **Flow Throttled** | ~25s | None | Multi-node pipelines |
| **Nested Throttled** | ~30s | None | Complex pipelines |

---

## Examples in This Directory

| File | Description |
|------|-------------|
| `main.py` | Basic batch translation with node throttling |
| `adaptive_example.py` | Adaptive node throttling demo |
| `presets_example.py` | Using rate limit presets |
| `flow_throttle_example.py` | Flow-level throttling |
| `parameterized_flow_example.py` | Different parameters per flow instance |
| `shared_limiter_example.py` | Shared rate limiters |
| `utils.py` | LLM API wrapper utilities |

## Running Examples

```bash
# Install dependencies
pip install -r requirements.txt

# Set API keys (if using real APIs)
export ANTHROPIC_API_KEY="your-key-here"
export OPENAI_API_KEY="your-key-here"

# Run examples
python main.py
python adaptive_example.py
python flow_throttle_example.py
python shared_limiter_example.py
```

## Requirements

```
pocketflow>=0.0.3
pocketflow-throttled>=0.2.0
anthropic>=0.18.0  # optional
openai>=1.0.0      # optional
python-dotenv>=1.0.0
```

---

## Decision Guide: Which Throttling to Use?

```
Do you have a single node processing items?
│
├── YES → Use ThrottledParallelBatchNode
│         (or AdaptiveThrottledNode for unknown limits)
│
└── NO (multi-node flow) → Do items need to be processed independently?
                           │
                           ├── YES → Use ThrottledAsyncParallelBatchFlow
                           │         (or AdaptiveThrottledBatchFlow)
                           │
                           └── NO (shared state) → Use regular AsyncFlow
                                                   with ThrottledParallelBatchNode

Do multiple nodes/flows share the same API?
│
├── YES → Use LimiterRegistry for global coordination
│
└── NO → Use per-node/flow throttling
```
