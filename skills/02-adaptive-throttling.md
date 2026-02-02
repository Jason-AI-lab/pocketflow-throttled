# Skill 02: Adaptive Throttling

**Difficulty**: Intermediate
**Source**: `cookbook/rate_limited_llm_batch/adaptive_example.py`

## When to Use

- You don't know the exact rate limits
- Rate limits change dynamically (time-based, load-based)
- Want automatic self-tuning without manual configuration
- Need to maximize throughput while avoiding rate limit errors

## Key Concepts

`AdaptiveThrottledNode` automatically adjusts its concurrency based on API responses:

1. **Backs off** when hitting rate limits (reduces concurrency)
2. **Recovers** after sustained success (increases concurrency)
3. **Self-tunes** to find the optimal throughput

This is a **state machine** that learns the API's actual limits.

## Core Pattern

```python
from pocketflow_throttled import AdaptiveThrottledNode

class MyAdaptiveNode(AdaptiveThrottledNode):
    # Starting configuration
    initial_concurrent = 10     # Start optimistic

    # Boundaries
    min_concurrent = 2          # Never go below this
    max_concurrent = 50         # Cap at this maximum

    # Backoff behavior (when rate limited)
    backoff_factor = 0.5        # Multiply current by this (halve)

    # Recovery behavior (after success)
    recovery_threshold = 10     # Consecutive successes needed
    recovery_factor = 1.2       # Multiply current by this (+20%)

    # Optional: also set throughput limit
    max_per_minute = 300        # Safety net

    async def exec_async(self, item):
        """Process item - rate limit detection happens automatically."""
        return await call_api(item)
```

## Complete Example: Self-Tuning API Caller

```python
from pocketflow_throttled import AdaptiveThrottledNode
from pocketflow import AsyncFlow

class AdaptiveTranslationNode(AdaptiveThrottledNode):
    """Automatically adjusts to API's actual rate limits."""

    # Start aggressive - will back off if needed
    initial_concurrent = 10

    # Conservative minimum - always safe
    min_concurrent = 2

    # Optimistic maximum - for high-tier accounts
    max_concurrent = 30

    # Aggressive backoff - halve on rate limit
    backoff_factor = 0.5

    # Gradual recovery - need 5 successes
    recovery_threshold = 5
    recovery_factor = 1.5  # +50% increase

    # Safety throughput limit
    max_per_minute = 200

    async def prep_async(self, shared):
        return shared.get("items", [])

    async def exec_async(self, item):
        """
        Rate limit detection is automatic.
        The node will detect rate limit errors and adapt.
        """
        try:
            return await call_api(item)
        except APIError as e:
            # Optionally override rate limit detection
            if "rate limit" in str(e).lower():
                # This will trigger backoff
                raise
            # Other errors are handled normally
            raise

    async def post_async(self, shared, prep_res, exec_res_list):
        shared["results"] = exec_res_list
        return "default"

# Usage with monitoring
async def process_with_adaptive_throttling():
    node = AdaptiveTranslationNode()
    flow = AsyncFlow(start=node)

    shared = {"items": list(range(100))}

    print(f"Starting with {node.initial_concurrent} concurrent")
    await flow.run_async(shared)

    # Check final stats
    stats = node.stats
    print(f"Final concurrent level: {stats['current_concurrent']}")
    print(f"Total rate limits hit: {stats['total_rate_limits']}")
    print(f"Total successes: {stats['total_successes']}")
```

## Adaptive Behavior Explained

### State Machine
```
                    ┌─────────────────┐
                    │   Initial: 10   │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
    ┌───────────────────┐         ┌─────────────────┐
    │  Hit Rate Limit   │         │   5 Successes   │
    │  Backoff × 0.5    │         │  Recover × 1.5  │
    │  10 → 5           │         │  10 → 15        │
    └───────┬───────────┘         └────────┬────────┘
            │                              │
            │      ┌──────────┐            │
            └─────▶│ Current │◀────────────┘
                   │  Value  │
                   └──────────┘
```

### Example Progression

```
Batch 1: Start at 10 concurrent
  → Hit rate limit
  → Backoff: 10 × 0.5 = 5

Batch 2: At 5 concurrent
  → All succeed
  → Success count: 5/10 (need 10 for recovery)

Batch 3: Still at 5 concurrent
  → All succeed
  → Success count: 10/10 ✓
  → Recover: 5 × 1.5 = 7.5 → 8

Batch 4: At 8 concurrent
  → Hit rate limit again
  → Backoff: 8 × 0.5 = 4

Final: Stabilizes around 4-6 concurrent (optimal for this API)
```

## Configuration Strategies

### Conservative (Start Low, Grow Slow)
```python
class ConservativeAdaptive(AdaptiveThrottledNode):
    initial_concurrent = 3      # Start safe
    min_concurrent = 1
    max_concurrent = 20
    backoff_factor = 0.5        # Halve on error
    recovery_threshold = 20     # Need many successes
    recovery_factor = 1.1       # Only +10%
```

### Moderate (Balanced)
```python
class ModerateAdaptive(AdaptiveThrottledNode):
    initial_concurrent = 10
    min_concurrent = 2
    max_concurrent = 50
    backoff_factor = 0.5
    recovery_threshold = 10
    recovery_factor = 1.2       # +20%
```

### Aggressive (Start High, Quick Recovery)
```python
class AggressiveAdaptive(AdaptiveThrottledNode):
    initial_concurrent = 20     # Start very high
    min_concurrent = 5
    max_concurrent = 100
    backoff_factor = 0.7        # Gentle backoff (only -30%)
    recovery_threshold = 5      # Quick recovery
    recovery_factor = 1.5       # +50% increase
```

## Custom Rate Limit Detection

Override `is_rate_limit_error()` for custom detection:

```python
class CustomDetectionNode(AdaptiveThrottledNode):
    def is_rate_limit_error(self, error: Exception) -> bool:
        """Custom logic to detect rate limit errors."""
        # Check for specific error messages
        if isinstance(error, APIError):
            return error.status_code == 429

        # Check error message
        error_msg = str(error).lower()
        return any(phrase in error_msg for phrase in [
            "rate limit",
            "too many requests",
            "quota exceeded",
            "throttled"
        ])
```

## Monitoring Adaptive Behavior

```python
async def monitor_adaptation():
    node = AdaptiveAdaptiveNode()

    # Process in batches to observe adaptation
    for batch_num in range(5):
        items = list(range(batch_num * 50, (batch_num + 1) * 50))
        shared = {"items": items}

        await node._run_async(shared)

        # Check stats after each batch
        stats = node.stats
        print(f"Batch {batch_num + 1}:")
        print(f"  Current concurrent: {stats['current_concurrent']}")
        print(f"  Total rate limits: {stats['total_rate_limits']}")
        print(f"  Consecutive successes: {stats['consecutive_successes']}")
```

## Available Statistics

```python
stats = node.stats
# Returns:
{
    'current_concurrent': 8,           # Current concurrency level
    'initial_concurrent': 10,          # Starting value
    'min_concurrent': 2,               # Floor
    'max_concurrent': 50,              # Ceiling
    'total_successes': 150,            # Total successful calls
    'total_rate_limits': 3,            # Times we hit rate limit
    'consecutive_successes': 12,       # Current success streak
    'recovery_threshold': 10,          # Successes needed for recovery
    'backoff_factor': 0.5,
    'recovery_factor': 1.2
}
```

## Propagating Rate Limits to Flows

When used in an adaptive flow, signal rate limits upward:

```python
class PropagatingNode(AdaptiveThrottledNode):
    # Enable automatic propagation
    propagate_rate_limit = True

    async def exec_async(self, item):
        """
        When this hits a rate limit:
        1. Backs off internally (node-level)
        2. Raises RateLimitHit for parent flow (flow-level)
        """
        return await call_api(item)

# Use in an adaptive flow
from pocketflow_throttled import AdaptiveThrottledBatchFlow

class SmartFlow(AdaptiveThrottledBatchFlow):
    initial_concurrent_flows = 10

    async def prep_async(self, shared):
        return [{"item": i} for i in range(100)]

flow = SmartFlow(start=PropagatingNode())
# Both flow AND node adapt independently
```

## Common Patterns

### Pattern: Unknown API Tier
```python
# Don't know if you're on free tier or paid tier
class UnknownTierNode(AdaptiveThrottledNode):
    initial_concurrent = 10     # Try moderate
    min_concurrent = 1          # Support free tier
    max_concurrent = 100        # Support enterprise tier
    # Will find the right level automatically
```

### Pattern: Variable Load API
```python
# API limits vary by time of day or system load
class VariableLoadNode(AdaptiveThrottledNode):
    initial_concurrent = 15
    min_concurrent = 3
    max_concurrent = 30
    recovery_threshold = 5      # Quick to adapt
    # Continuously adapts to current conditions
```

### Pattern: Multi-Tenant System
```python
# Different customers have different quotas
class MultiTenantNode(AdaptiveThrottledNode):
    # Each customer gets their own node instance
    initial_concurrent = 10
    min_concurrent = 2
    max_concurrent = 50
    # Adapts to each customer's quota
```

## Comparison: Fixed vs Adaptive

| Aspect | Fixed (Skill 01) | Adaptive (Skill 02) |
|--------|------------------|---------------------|
| Setup | Need to know limits | Works without knowing |
| Performance | Optimal if limits correct | Finds optimal automatically |
| Safety | Safe if conservative | Very safe (backs off on error) |
| Complexity | Simple | More complex |
| Best for | Known, stable limits | Unknown or variable limits |

## Related Skills

- **Simpler**: [Skill 01: Basic Node Throttling](01-basic-node-throttling.md) - If you know limits
- **Flow-level**: [Skill 03: Flow-Level Throttling](03-flow-level-throttling.md) - Adaptive flows
- **Presets**: [Skill 06: Using Presets](06-using-presets.md) - Starting configurations

## When NOT to Use

- **Known, stable rate limits** → Use [Basic Throttling](01-basic-node-throttling.md)
- **Need guaranteed throughput** → Use fixed limits
- **Cost-sensitive (testing)** → Start with fixed limits, then enable adaptive
