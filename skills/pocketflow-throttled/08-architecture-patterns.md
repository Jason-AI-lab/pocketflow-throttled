---
name: "architecture-patterns"
description: "Core design patterns and flow mechanics for pocketflow-throttled. Use to understand the underlying architecture and design principles."
---

# Skill 08: Architecture Patterns

**Difficulty**: Advanced
**Source**: `docs/AsyncFlow_specifications.md`, `docs/flows_in_pocketflow.md`, `docs/parameter_passing_mechanism.md`

## Core Concepts

This skill explains the foundational architecture and design patterns of `pocketflow-throttled`.

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│          User Code (Nodes/Flows)                │
├─────────────────────────────────────────────────┤
│   ThrottledParallelBatchNode                    │
│   AdaptiveThrottledNode                         │
│   ThrottledAsyncParallelBatchFlow               │
│   AdaptiveThrottledBatchFlow                    │
├─────────────────────────────────────────────────┤
│   RateLimiter (Token Bucket + Sliding Window)   │
│   LimiterRegistry (Global shared limiters)      │
├─────────────────────────────────────────────────┤
│   Presets / FlowPresets (Configuration)         │
│   RateLimitHit (Signaling Exception)            │
└─────────────────────────────────────────────────┘
```

## Key Design Patterns

### 1. Lazy Limiter Initialization

**Pattern**: Limiters are created on first access, not in `__init__`.

**Why**: Allows nodes to be instantiated without connecting to the event loop.

```python
class ThrottledParallelBatchNode:
    def __init__(self):
        self._limiter = None  # Not created yet

    @property
    def limiter(self):
        """Lazy initialization - created on first access."""
        if self._limiter is None:
            self._limiter = RateLimiter(
                max_concurrent=self.max_concurrent,
                max_per_window=self.max_per_minute,
                window_seconds=60.0
            )
        return self._limiter

    def reset_limiter(self):
        """Call this between runs to reset state."""
        self._limiter = None
```

**Usage Implication**: Reset between runs:
```python
node = MyNode()
await node._run_async(shared1)
node.reset_limiter()  # Important!
await node._run_async(shared2)
```

### 2. Two-Mode Throttling

**Pattern**: Combines semaphore (concurrency) + sliding window (throughput).

```python
class RateLimiter:
    def __init__(self, max_concurrent, max_per_window, window_seconds):
        # Mode 1: Concurrency control
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Mode 2: Throughput control
        self._max_per_window = max_per_window
        self._window = window_seconds
        self._timestamps = deque()  # Track recent requests

    async def __aenter__(self):
        # 1. Wait for semaphore (concurrent limit)
        await self._semaphore.acquire()

        # 2. Wait for window (throughput limit)
        await self._wait_for_window()

    async def _wait_for_window(self):
        """Wait until we're under the window limit."""
        while True:
            now = time.monotonic()

            # Remove old timestamps outside window
            while self._timestamps and self._timestamps[0] < now - self._window:
                self._timestamps.popleft()

            # Check if under limit
            if len(self._timestamps) < self._max_per_window:
                self._timestamps.append(now)
                break

            # Wait a bit before checking again
            await asyncio.sleep(0.1)
```

**Why Both**:
- **Semaphore**: Prevents too many simultaneous operations (resource exhaustion)
- **Sliding window**: Prevents burst patterns exceeding rate limits

### 3. Adaptive State Machine

**Pattern**: Track consecutive successes/failures, adjust concurrency dynamically.

```python
class AdaptiveThrottledNode:
    def __init__(self):
        self._current_concurrent = self.initial_concurrent
        self._consecutive_successes = 0
        self._total_successes = 0
        self._total_rate_limits = 0
        self._lock = asyncio.Lock()  # Thread-safety

    async def _on_rate_limit(self):
        """Called when rate limit detected."""
        async with self._lock:
            # Backoff: reduce concurrency
            new_value = max(
                self.min_concurrent,
                int(self._current_concurrent * self.backoff_factor)
            )
            self._current_concurrent = new_value

            # Reset success counter
            self._consecutive_successes = 0
            self._total_rate_limits += 1

    async def _on_success(self):
        """Called on successful operation."""
        async with self._lock:
            self._consecutive_successes += 1
            self._total_successes += 1

            # Recovery: increase concurrency after sustained success
            if self._consecutive_successes >= self.recovery_threshold:
                new_value = min(
                    self.max_concurrent,
                    int(self._current_concurrent * self.recovery_factor)
                )
                self._current_concurrent = new_value
                self._consecutive_successes = 0  # Reset counter
```

**State Transitions**:
```
[Initial: 10] ─┬─→ [Success] ─┬─→ Count++
               │               │
               │               └─→ Count=10 ─→ [Recover: 10×1.2=12]
               │
               └─→ [Rate Limit] ─→ [Backoff: 10×0.5=5]
                                    Count=0
```

### 4. Node-to-Flow Signaling

**Pattern**: Nodes raise `RateLimitHit` exception to signal flow-level adaptation.

```python
# In AdaptiveThrottledNode
class AdaptiveThrottledNode:
    propagate_rate_limit = False  # Default: don't propagate

    async def _exec_with_rate_limit_detection(self, item):
        try:
            result = await self.exec_async(item)
            await self._on_success()
            return result
        except Exception as e:
            if self.is_rate_limit_error(e):
                await self._on_rate_limit()

                # Optionally propagate to parent flow
                if self.propagate_rate_limit:
                    raise RateLimitHit("Rate limit in node") from e

            raise

# In AdaptiveThrottledBatchFlow
class AdaptiveThrottledBatchFlow:
    async def _run_single_flow(self, params):
        try:
            result = await self._orch_async(shared, params)
            await self._on_flow_success()
            return result
        except RateLimitHit:
            # Flow-level adaptation triggered by node signal
            await self._on_flow_rate_limit()
            raise
```

**Layered Adaptation**:
```
Node hits rate limit
│
├─→ Node backs off (10 → 5 concurrent)
│
└─→ If propagate_rate_limit=True:
    └─→ Flow also backs off (15 → 7 flows)
```

### 5. Override Pattern for Custom Detection

**Pattern**: Override `is_rate_limit_error()` for custom rate limit detection.

```python
class CustomDetectionNode(AdaptiveThrottledNode):
    def is_rate_limit_error(self, error: Exception) -> bool:
        """Override to detect custom rate limit signals."""

        # Check HTTP status code
        if hasattr(error, 'status_code'):
            if error.status_code == 429:
                return True

        # Check error message
        error_msg = str(error).lower()
        keywords = ['rate limit', 'too many requests', 'quota exceeded', 'throttled']

        if any(kw in error_msg for kw in keywords):
            return True

        # Check custom headers
        if hasattr(error, 'headers'):
            if 'X-RateLimit-Remaining' in error.headers:
                if int(error.headers['X-RateLimit-Remaining']) == 0:
                    return True

        return False
```

### 6. Flow Class Hierarchy

```
BaseNode
  │
  ├── Node (retry logic)
  │     ├── BatchNode
  │     └── AsyncNode
  │           ├── AsyncBatchNode
  │           └── AsyncParallelBatchNode
  │
  └── Flow (orchestrates nodes)
        │
        ├── BatchFlow (runs flow N times sequentially)
        │
        └── AsyncFlow (async orchestration)
              │
              ├── AsyncBatchFlow (sequential async batches)
              │
              └── AsyncParallelBatchFlow (parallel async batches)
```

**Key Differences**:

| Flow Type | Batch? | Parallel? | Node Execution |
|-----------|--------|-----------|----------------|
| `AsyncFlow` | No | No | Sequential nodes |
| `AsyncBatchFlow` | Yes | No | Sequential flow instances |
| `AsyncParallelBatchFlow` | Yes | Yes | Parallel flow instances |

### 7. Parameter Flow Mechanism

**How parameters reach nodes in `ThrottledAsyncParallelBatchFlow`**:

```python
# Step 1: prep_async returns list of param dicts
async def prep_async(self, shared):
    return [
        {"user_id": 1},
        {"user_id": 2},
        {"user_id": 3}
    ]

# Step 2: Each dict becomes params for one flow instance
async def _run_async(self, shared):
    pr = await self.prep_async(shared)

    # Launch parallel flow instances
    await asyncio.gather(*(
        self._orch_async(shared, {**self.params, **bp})  # Merge params
        for bp in pr
    ))

# Step 3: _orch_async sets params on each node
async def _orch_async(self, shared, params):
    curr = copy.copy(self.start_node)  # Copy node for this instance
    p = params  # Merged params

    while curr:
        curr.set_params(p)  # Set params on node
        result = await curr._run_async(shared)
        curr = self.get_next_node(curr, result)

# Step 4: Node accesses params
class MyNode(AsyncNode):
    async def exec_async(self, _):
        user_id = self.params["user_id"]  # Set by _orch_async
```

**Visualization**:
```
prep_async() → [{"user_id": 1}, {"user_id": 2}]
                │
                ├─→ Flow Instance 1
                │   params = {"user_id": 1}
                │   │
                │   ├─→ NodeA.params = {"user_id": 1}
                │   └─→ NodeB.params = {"user_id": 1}
                │
                └─→ Flow Instance 2
                    params = {"user_id": 2}
                    │
                    ├─→ NodeA.params = {"user_id": 2}
                    └─→ NodeB.params = {"user_id": 2}
```

## Important Implementation Details

### AsyncFlow Node Execution

**Nodes execute sequentially, not in parallel**:

```python
async def _orch_async(self, shared, params):
    while curr:  # Sequential loop!
        curr.set_params(params)
        # Wait for current node to complete
        result = await curr._run_async(shared)
        # Only then move to next
        curr = self.get_next_node(curr, result)
```

**Parallelism happens**:
- **Within a node**: `AsyncParallelBatchNode` uses `asyncio.gather()`
- **Across flow instances**: `AsyncParallelBatchFlow` runs multiple flows

### Node Copying

**Why `copy.copy(self.start_node)`?**

```python
# Each flow instance needs its own node objects
curr = copy.copy(self.start_node)

# Without copy: All instances share same node
# → Setting params on one overwrites another's!

# With copy: Each instance has separate node objects
# → Each can have different params safely
```

### Monotonic Time

**Always use `time.monotonic()` not `time.time()`**:

```python
# Good: Monotonic time (unaffected by clock adjustments)
now = time.monotonic()

# Bad: Wall clock time (can go backwards!)
now = time.time()
```

**Why**: System clock can be adjusted (NTP, manual change). Monotonic time guarantees forward progress.

### Async Locks for State

**All state updates use `asyncio.Lock`**:

```python
class AdaptiveThrottledNode:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._current_concurrent = 10

    async def _on_rate_limit(self):
        async with self._lock:  # Thread-safe
            self._current_concurrent = int(self._current_concurrent * 0.5)
```

**Why**: Multiple coroutines might update state simultaneously.

### Return Exceptions

**Flows use `return_exceptions=True`**:

```python
results = await asyncio.gather(
    *(self._run_flow(bp) for bp in params),
    return_exceptions=True  # Don't fail all on one error
)
```

**Why**: One flow failure shouldn't cancel others. Errors are collected and handled.

## Registry Pattern

**LimiterRegistry is a singleton**:

```python
class _LimiterRegistry:
    _instance = None
    _limiters = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, name, **kwargs):
        self._limiters[name] = RateLimiter(**kwargs)

    def get(self, name):
        return self._limiters[name]

# Global singleton
LimiterRegistry = _LimiterRegistry()
```

**Implications**:
- One global registry per process
- Thread-safe (with locks)
- Persists for application lifetime
- Use `reset()` for testing

## Configuration Flow

### Presets → Node

```python
# 1. Preset defined
Presets.OPENAI_TIER1 = {
    "max_concurrent": 5,
    "max_per_minute": 60
}

# 2. Applied to node
class MyNode(ThrottledParallelBatchNode):
    max_concurrent = Presets.OPENAI_TIER1["max_concurrent"]
    max_per_minute = Presets.OPENAI_TIER1["max_per_minute"]

# 3. Node creates limiter
@property
def limiter(self):
    return RateLimiter(
        max_concurrent=self.max_concurrent,      # 5
        max_per_window=self.max_per_minute,      # 60
        window_seconds=60.0
    )
```

## Common Patterns Summary

| Pattern | Purpose | When to Use |
|---------|---------|-------------|
| Lazy initialization | Defer limiter creation | Always (built-in) |
| Two-mode throttling | Control concurrency + throughput | Always (built-in) |
| Adaptive state machine | Auto-tune concurrency | Unknown/variable limits |
| Node-to-flow signaling | Multi-layer adaptation | Complex pipelines |
| Override detection | Custom rate limit logic | Non-standard APIs |
| Registry pattern | Share limiters globally | Multiple services/components |

## Best Practices from Architecture

1. **Always reset limiters** between independent runs
2. **Use monotonic time** for all timing operations
3. **Protect state with locks** when updating shared state
4. **Copy nodes** for parallel flow instances
5. **Return exceptions** from gather to avoid cascading failures
6. **Lazy initialize** to avoid event loop issues
7. **Use unique keys** in shared dict (race condition safety)

## Debugging Architecture

### Check Limiter State
```python
node = MyNode()
limiter = node.limiter  # Triggers lazy init

# Inspect internal state
print(f"Semaphore value: {limiter._semaphore._value}")
print(f"Window timestamps: {len(limiter._timestamps)}")
```

### Monitor Adaptive Behavior
```python
node = AdaptiveNode()
# ... run some operations ...

stats = node.stats
print(f"Current concurrent: {stats['current_concurrent']}")
print(f"Total rate limits: {stats['total_rate_limits']}")
print(f"Consecutive successes: {stats['consecutive_successes']}")
```

### Trace Parameter Flow
```python
class DebugNode(AsyncNode):
    async def exec_async(self, _):
        print(f"Node received params: {self.params}")
```

## Related Skills

All other skills build on these architectural patterns:

- [Skill 01: Basic Node Throttling](01-basic-node-throttling.md) - Uses lazy initialization, two-mode throttling
- [Skill 02: Adaptive Throttling](02-adaptive-throttling.md) - Uses adaptive state machine
- [Skill 03: Flow-Level Throttling](03-flow-level-throttling.md) - Uses parameter flow, node copying
- [Skill 04: Shared Limiters](04-shared-limiters.md) - Uses registry pattern
- [Skill 05: Parameterized Flows](05-parameterized-flows.md) - Uses parameter flow mechanism
- [Skill 07: Nested Throttling](07-nested-throttling.md) - Combines multiple patterns

## Deep Dive: Why These Choices?

### Why Lazy Initialization?
- Nodes can be instantiated before event loop exists
- Supports serialization/deserialization
- Allows testing without async context

### Why Two-Mode Throttling?
- Semaphore: Simple, fast concurrency control
- Sliding window: Precise throughput limiting
- Together: Handle both resource exhaustion AND API rate limits

### Why Adaptive?
- APIs don't always document exact limits
- Limits can change (tier upgrades, time-of-day)
- Self-tuning maximizes throughput without errors

### Why Node Copying?
- Each flow instance needs independent node state
- Shallow copy is sufficient (methods are shared, state is not)
- Allows different params per instance

### Why Monotonic Time?
- Wall clock can jump backwards (NTP, manual adjustment)
- Monotonic time always moves forward
- Critical for accurate rate limiting

This architectural foundation makes all the patterns in other skills possible!
