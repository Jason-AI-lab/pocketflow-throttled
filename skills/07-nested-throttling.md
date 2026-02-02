# Skill 07: Nested Throttling

**Difficulty**: Advanced
**Source**: `cookbook/rate_limited_llm_batch/flow_throttle_example.py`

## When to Use

- Each item requires a **multi-node pipeline**
- Each node in the pipeline makes **multiple API calls**
- Need **fine-grained control** at both flow and node levels
- Want to limit both "concurrent items" AND "concurrent calls per item"

## Key Concepts

**Nested throttling** combines:
1. **Flow-level throttling**: Limits concurrent items being processed
2. **Node-level throttling**: Limits concurrent API calls per item

This creates a **two-layer rate limiting system**.

## Core Pattern

```python
from pocketflow_throttled import (
    ThrottledAsyncParallelBatchFlow,
    ThrottledParallelBatchNode
)

# ═══════════════════════════════════════════════════
# Layer 1: Throttled Node (limits calls per item)
# ═══════════════════════════════════════════════════
class FetchUserDataNode(ThrottledParallelBatchNode):
    """Each user needs multiple API calls - throttle at node level."""

    max_concurrent = 3      # Max 3 API calls per user
    max_per_minute = 30     # Max 30 calls per minute per user

    async def prep_async(self, shared):
        user_id = self.params["user_id"]  # From flow params

        # Return list of API endpoints to call for this user
        return [
            f"/users/{user_id}/profile",
            f"/users/{user_id}/orders",
            f"/users/{user_id}/preferences",
            f"/users/{user_id}/notifications",
        ]

    async def exec_async(self, endpoint):
        """Called once per endpoint with rate limiting."""
        return await call_api(endpoint)

    async def post_async(self, shared, prep_res, exec_res_list):
        user_id = self.params["user_id"]
        shared.setdefault("user_data", {})[user_id] = exec_res_list
        return "default"

# ═══════════════════════════════════════════════════
# Layer 2: Throttled Flow (limits concurrent users)
# ═══════════════════════════════════════════════════
class UserBatchFlow(ThrottledAsyncParallelBatchFlow):
    """Process many users - throttle at flow level."""

    max_concurrent_flows = 5  # Process 5 users at once

    async def prep_async(self, shared):
        # One flow instance per user
        return [{"user_id": uid} for uid in shared["user_ids"]]

# ═══════════════════════════════════════════════════
# Effective Limits
# ═══════════════════════════════════════════════════
# - Max 5 users processed concurrently (flow level)
# - Each user makes max 3 concurrent API calls (node level)
# - Total max concurrent API calls: 5 × 3 = 15
# ═══════════════════════════════════════════════════

# Usage
flow = UserBatchFlow(start=FetchUserDataNode())
await flow.run_async({"user_ids": list(range(100))})
```

## Complete Example: Document Processing Pipeline

```python
from pocketflow import AsyncNode
from pocketflow_throttled import (
    ThrottledAsyncParallelBatchFlow,
    ThrottledParallelBatchNode
)

# ═══════════════════════════════════════════════════
# Node 1: Fetch document chunks (throttled)
# ═══════════════════════════════════════════════════
class FetchDocumentChunksNode(ThrottledParallelBatchNode):
    """
    Each document is split into chunks.
    Fetch all chunks in parallel with throttling.
    """
    max_concurrent = 5      # Max 5 chunks fetched per document
    max_per_minute = 100    # Safety limit

    async def prep_async(self, shared):
        doc_id = self.params["doc_id"]
        chunk_count = self.params["chunk_count"]

        # Return list of chunk IDs to fetch
        return [f"{doc_id}/chunk_{i}" for i in range(chunk_count)]

    async def exec_async(self, chunk_id):
        """Fetch one chunk."""
        return await storage_api.get(chunk_id)

    async def post_async(self, shared, prep_res, exec_res_list):
        doc_id = self.params["doc_id"]
        # Combine chunks
        shared.setdefault("documents", {})[doc_id] = "".join(exec_res_list)
        return "analyze"

# ═══════════════════════════════════════════════════
# Node 2: Analyze with LLM (throttled)
# ═══════════════════════════════════════════════════
class AnalyzeChunksNode(ThrottledParallelBatchNode):
    """
    Analyze document in multiple passes.
    Each pass is an LLM call.
    """
    max_concurrent = 2      # Max 2 LLM calls per document
    max_per_minute = 60     # Match LLM API limits

    async def prep_async(self, shared):
        doc_id = self.params["doc_id"]
        document = shared["documents"][doc_id]

        # Different analysis types
        return [
            ("sentiment", document),
            ("entities", document),
            ("summary", document),
        ]

    async def exec_async(self, item):
        """Perform one analysis."""
        analysis_type, text = item
        return await llm_api.analyze(text, analysis_type)

    async def post_async(self, shared, prep_res, exec_res_list):
        doc_id = self.params["doc_id"]
        shared.setdefault("analyses", {})[doc_id] = {
            "sentiment": exec_res_list[0],
            "entities": exec_res_list[1],
            "summary": exec_res_list[2],
        }
        return "default"

# ═══════════════════════════════════════════════════
# Throttled Flow: Process many documents
# ═══════════════════════════════════════════════════
class DocumentProcessingFlow(ThrottledAsyncParallelBatchFlow):
    """
    Process many documents with nested throttling.

    Flow level: Max 10 documents processed concurrently
    Node level: Each document's chunks/analyses throttled independently
    """
    max_concurrent_flows = 10       # 10 documents at once
    max_flows_per_minute = 60       # Start max 60 docs per minute

    async def prep_async(self, shared):
        documents = shared["documents"]

        return [
            {
                "doc_id": doc.id,
                "chunk_count": doc.chunk_count
            }
            for doc in documents
        ]

# ═══════════════════════════════════════════════════
# Build and run
# ═══════════════════════════════════════════════════
fetch = FetchDocumentChunksNode()
analyze = AnalyzeChunksNode()
fetch - "analyze" >> analyze

flow = DocumentProcessingFlow(start=fetch)
await flow.run_async({"documents": [...]})

# Effective limits:
# - 10 documents processed concurrently (flow)
# - Per document:
#     - 5 chunks fetched concurrently (fetch node)
#     - 2 analyses run concurrently (analyze node)
# - Max API calls:
#     - Storage: 10 docs × 5 chunks = 50 concurrent
#     - LLM: 10 docs × 2 analyses = 20 concurrent
```

## Execution Model

### Without Nested Throttling
```
100 documents, no throttling:
└── All 100 start immediately
    ├── Each fetches 10 chunks = 1000 concurrent storage API calls ❌
    └── Each runs 3 analyses = 300 concurrent LLM calls ❌
Result: Overwhelmed APIs, many 429 errors
```

### With Flow-Only Throttling
```
100 documents, flow throttled (10 concurrent):
└── 10 documents at once
    ├── Each fetches 10 chunks = 100 concurrent storage calls ⚠️ (still high)
    └── Each runs 3 analyses = 30 concurrent LLM calls ⚠️ (still high)
Result: Better, but node-level calls still too high
```

### With Nested Throttling ✅
```
100 documents, flow (10) + node throttling (5 chunks, 2 analyses):
└── 10 documents at once (flow level)
    ├── Each fetches max 5 chunks = 50 concurrent storage calls ✓
    └── Each runs max 2 analyses = 20 concurrent LLM calls ✓
Result: Controlled at both levels
```

## Calculating Effective Limits

### Formula
```
Total Concurrent API Calls =
    max_concurrent_flows × max_concurrent_per_node

Total Throughput =
    min(
        max_flows_per_minute × calls_per_flow,
        max_per_minute_per_node × max_concurrent_flows
    )
```

### Example 1: Simple Nested
```python
# Flow: 5 concurrent flows
# Node: 3 concurrent calls per flow
# = 5 × 3 = 15 total concurrent API calls
```

### Example 2: Multiple Nodes
```python
# Flow: 10 concurrent flows
# Node A: 4 concurrent calls per flow
# Node B: 2 concurrent calls per flow

# If A and B run sequentially:
# Max concurrent = max(10×4, 10×2) = 40

# If A and B can overlap (rare):
# Max concurrent = 10×4 + 10×2 = 60
```

## Common Patterns

### Pattern: Multi-Stage Pipeline with Different Limits

```python
# Stage 1: Heavy I/O, allow more concurrency
class FetchStage(ThrottledParallelBatchNode):
    max_concurrent = 10     # Many parallel fetches OK

# Stage 2: CPU/API intensive, limit concurrency
class ProcessStage(ThrottledParallelBatchNode):
    max_concurrent = 2      # Expensive processing

# Stage 3: Simple storage, allow more
class StoreStage(ThrottledParallelBatchNode):
    max_concurrent = 5

# Flow: Moderate item concurrency
class Pipeline(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = 8

# Effective limits vary by stage:
# - Fetch: 8 items × 10 fetches = 80 concurrent
# - Process: 8 items × 2 processes = 16 concurrent
# - Store: 8 items × 5 stores = 40 concurrent
```

### Pattern: Adaptive Flow + Fixed Nodes

```python
from pocketflow_throttled import AdaptiveThrottledBatchFlow

class AdaptiveFlow(AdaptiveThrottledBatchFlow):
    """Flow adapts, but nodes have fixed limits."""

    initial_concurrent_flows = 10
    min_concurrent_flows = 2
    max_concurrent_flows = 50

class FixedLimitNode(ThrottledParallelBatchNode):
    """Node keeps stable limits regardless of flow adaptation."""
    max_concurrent = 5
    max_per_minute = 60

# As flow adapts (2-50 concurrent items),
# each item still respects fixed 5 concurrent calls
```

### Pattern: Fixed Flow + Adaptive Nodes

```python
from pocketflow_throttled import AdaptiveThrottledNode

class FixedFlow(ThrottledAsyncParallelBatchFlow):
    """Flow has fixed concurrency."""
    max_concurrent_flows = 10

class AdaptiveAPINode(AdaptiveThrottledNode):
    """Node adapts to API conditions."""
    initial_concurrent = 5
    min_concurrent = 1
    max_concurrent = 20

# 10 items always processing,
# but each adapts its internal API call rate
```

### Pattern: Region-Specific Nested Limits

```python
class RegionalFlow(ThrottledAsyncParallelBatchFlow):
    def __init__(self, region: str):
        # Different regions have different flow limits
        limits = {
            "us": {"max_concurrent_flows": 20},
            "eu": {"max_concurrent_flows": 10},
            "asia": {"max_concurrent_flows": 5},
        }
        super().__init__(**limits[region])

class RegionalNode(ThrottledParallelBatchNode):
    def __init__(self, region: str):
        # Different regions have different node limits
        limits = {
            "us": {"max_concurrent": 10, "max_per_minute": 200},
            "eu": {"max_concurrent": 5, "max_per_minute": 100},
            "asia": {"max_concurrent": 3, "max_per_minute": 60},
        }
        super().__init__(**limits[region])
```

## Monitoring Nested Throttling

```python
async def run_with_monitoring():
    flow = DocumentProcessingFlow(start=fetch_node)

    await flow.run_async({"documents": docs})

    # Flow-level stats
    flow_stats = flow.stats
    print(f"Flow stats:")
    print(f"  Max concurrent flows: {flow_stats['max_concurrent_flows']}")
    print(f"  Completed flows: {flow_stats['completed_flows']}")

    # Node-level stats (if nodes are accessible)
    node_stats = fetch_node.stats
    print(f"\nFetch node stats:")
    print(f"  Max concurrent: {node_stats.get('max_concurrent', 'N/A')}")
```

## Tuning Nested Limits

### Start Conservative
```python
# Week 1: Start safe
class SafeFlow(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = 5

class SafeNode(ThrottledParallelBatchNode):
    max_concurrent = 2
# Total: 5 × 2 = 10 concurrent calls
```

### Gradually Increase
```python
# Week 2: Increase flow level
max_concurrent_flows = 10  # Was 5
# Total: 10 × 2 = 20 concurrent calls

# Week 3: Increase node level
max_concurrent = 3  # Was 2
# Total: 10 × 3 = 30 concurrent calls

# Week 4: Fine-tune both
max_concurrent_flows = 15
max_concurrent = 4
# Total: 15 × 4 = 60 concurrent calls
```

### Monitor and Adjust
```python
# If seeing rate limits at flow level:
# → Decrease max_concurrent_flows

# If seeing rate limits at node level:
# → Decrease max_concurrent in nodes

# If both stable but want more throughput:
# → Increase both proportionally
```

## Comparison: Single vs Nested Throttling

| Scenario | Single Throttling | Nested Throttling |
|----------|------------------|-------------------|
| Simple batch (one API call per item) | ✅ Use node throttling | ❌ Overkill |
| Multi-node pipeline (one call per node) | ✅ Use flow throttling | ⚠️ Optional |
| Multi-call nodes in pipeline | ⚠️ Hard to control | ✅ **Use nested** |
| Complex quota management | ⚠️ Limited control | ✅ **Use nested** |

## Common Mistakes

### ❌ Over-Constraining
```python
# Too restrictive - won't utilize available quota
class OverConstrained(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = 2  # Very low

class StrictNode(ThrottledParallelBatchNode):
    max_concurrent = 1  # Very low

# Total: Only 2 concurrent API calls (too slow!)
```

### ❌ Under-Constraining
```python
# Too loose - will hit rate limits
class UnderConstrained(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = 100  # Way too high

class LooseNode(ThrottledParallelBatchNode):
    max_concurrent = 50  # Way too high

# Total: 5000 concurrent API calls (will fail!)
```

### ❌ Forgetting Total Calculation
```python
# Seems reasonable individually
max_concurrent_flows = 20
max_concurrent = 10

# But total = 20 × 10 = 200 concurrent calls!
# Might exceed API limits
```

## Best Practices

1. **Calculate totals** - Always compute `flows × calls_per_flow`
2. **Monitor both levels** - Track stats at flow and node level
3. **Start conservative** - Begin with low limits, increase gradually
4. **Test with realistic data** - Ensure limits work with actual workload
5. **Document the math** - Comment why you chose specific limits

## Related Skills

- **Foundation**: [Skill 01: Basic Node Throttling](01-basic-node-throttling.md)
- **Foundation**: [Skill 03: Flow-Level Throttling](03-flow-level-throttling.md)
- **Advanced**: [Skill 04: Shared Limiters](04-shared-limiters.md) - Add third layer
- **Architecture**: [Skill 08: Architecture Patterns](08-architecture-patterns.md)

## When NOT to Use

- **Simple batches** → Use [Node Throttling](01-basic-node-throttling.md) only
- **Single API call per item** → Use [Flow Throttling](03-flow-level-throttling.md) only
- **Adds unnecessary complexity** → Prefer simpler patterns
