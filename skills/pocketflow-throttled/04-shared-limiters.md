---
name: "shared-limiters"
description: "Global rate limiter coordination across components. Use when multiple services share the same API quota."
---

# Skill 04: Shared Limiters

**Difficulty**: Advanced
**Source**: `cookbook/rate_limited_llm_batch/shared_limiter_example.py`

## When to Use

- Multiple nodes/flows calling the **same API**
- Need **global** rate limit coordination across your application
- Different components must respect the **same quota**
- Want to prevent one component from exhausting the quota for others

## Key Concepts

`LimiterRegistry` provides a global singleton registry for sharing rate limiters:

1. **Register once** at application startup
2. **Access anywhere** by name
3. **Shared limit** applies across all users of the limiter
4. **Thread-safe** coordination

**Critical**: All components using the same named limiter share its concurrency and throughput limits.

## Core Pattern

```python
from pocketflow_throttled import LimiterRegistry
from pocketflow import AsyncNode

# ═══════════════════════════════════════════════════
# Step 1: Register at application startup (ONCE)
# ═══════════════════════════════════════════════════
LimiterRegistry.register(
    "openai",                  # Name to reference it by
    max_concurrent=10,         # Total concurrent across all users
    max_per_window=60,         # Total per minute across all users
    window_seconds=60.0        # Window duration
)

# ═══════════════════════════════════════════════════
# Step 2: Use anywhere in your code
# ═══════════════════════════════════════════════════
class ServiceA(AsyncNode):
    async def exec_async(self, item):
        # Use the shared limiter
        async with LimiterRegistry.get("openai"):
            return await call_openai(item)

class ServiceB(AsyncNode):
    async def exec_async(self, item):
        # Same limiter - total concurrent <= 10 across BOTH services
        async with LimiterRegistry.get("openai"):
            return await call_openai(item)
```

## Complete Example: Multi-Service Coordination

```python
from pocketflow import AsyncNode, AsyncFlow
from pocketflow_throttled import (
    LimiterRegistry,
    ThrottledAsyncParallelBatchFlow
)

# ═══════════════════════════════════════════════════
# Setup: Register limiters at app startup
# ═══════════════════════════════════════════════════
def setup_limiters():
    """Call this once when your application starts."""

    # OpenAI API - shared across all services
    LimiterRegistry.register(
        "openai",
        max_concurrent=10,
        max_per_window=60,
        window_seconds=60.0
    )

    # Anthropic API - different limits
    LimiterRegistry.register(
        "anthropic",
        max_concurrent=5,
        max_per_window=50,
        window_seconds=60.0
    )

    # Internal API - no throughput limit
    LimiterRegistry.register(
        "internal_api",
        max_concurrent=20,
        max_per_window=None  # No throughput limit
    )

# Call at startup
setup_limiters()

# ═══════════════════════════════════════════════════
# Service 1: Translation Service
# ═══════════════════════════════════════════════════
class TranslationNode(AsyncNode):
    """Uses OpenAI for translation."""

    async def exec_async(self, _):
        text = self.params["text"]
        target = self.params["target_language"]

        # Uses shared "openai" limiter
        async with LimiterRegistry.get("openai"):
            result = await openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": f"Translate to {target}: {text}"}]
            )

        return result.choices[0].message.content

# ═══════════════════════════════════════════════════
# Service 2: Summarization Service
# ═══════════════════════════════════════════════════
class SummarizationNode(AsyncNode):
    """Uses OpenAI for summarization."""

    async def exec_async(self, _):
        document = self.params["document"]

        # Uses THE SAME shared "openai" limiter
        # Total concurrent calls to OpenAI across both services <= 10
        async with LimiterRegistry.get("openai"):
            result = await openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": f"Summarize: {document}"}]
            )

        return result.choices[0].message.content

# ═══════════════════════════════════════════════════
# Usage: Both services respect shared limit
# ═══════════════════════════════════════════════════
async def run_services():
    # Translation flow (processes 20 items)
    class TranslationFlow(ThrottledAsyncParallelBatchFlow):
        max_concurrent_flows = 15  # Want to run 15 at once

        async def prep_async(self, shared):
            return [{"text": t, "target_language": "es"} for t in shared["texts"]]

    # Summarization flow (processes 20 items)
    class SummarizationFlow(ThrottledAsyncParallelBatchFlow):
        max_concurrent_flows = 15  # Want to run 15 at once

        async def prep_async(self, shared):
            return [{"document": d} for d in shared["documents"]]

    # Run both concurrently
    await asyncio.gather(
        TranslationFlow(start=TranslationNode()).run_async({"texts": [...]}),
        SummarizationFlow(start=SummarizationNode()).run_async({"documents": [...]})
    )

    # Even though each flow wants 15 concurrent,
    # the shared limiter ensures total OpenAI calls <= 10
```

## Registry Operations

### Register a Limiter
```python
LimiterRegistry.register(
    name="my_api",
    max_concurrent=10,
    max_per_window=100,
    window_seconds=60.0
)
```

### Get a Limiter
```python
limiter = LimiterRegistry.get("my_api")
async with limiter:
    result = await call_api()
```

### Get or Create (Lazy Registration)
```python
# Creates if doesn't exist, returns existing if it does
limiter = LimiterRegistry.get_or_create(
    "my_api",
    max_concurrent=10,
    max_per_window=100,
    window_seconds=60.0
)
```

### Check if Exists
```python
if LimiterRegistry.exists("my_api"):
    limiter = LimiterRegistry.get("my_api")
else:
    LimiterRegistry.register("my_api", ...)
```

### List All Limiters
```python
# Get all registered names
names = LimiterRegistry.list_names()
# ["openai", "anthropic", "internal_api"]

# Get all configs
configs = LimiterRegistry.list_all()
# {
#     "openai": {"max_concurrent": 10, "max_per_window": 60, ...},
#     "anthropic": {"max_concurrent": 5, ...}
# }
```

### Get Statistics
```python
stats = LimiterRegistry.stats("openai")
# {
#     'max_concurrent': 10,
#     'max_per_window': 60,
#     'current_window_count': 23,  # Current requests in window
#     'window_seconds': 60.0
# }
```

### Reset Registry (Testing)
```python
# Remove all limiters (useful for tests)
LimiterRegistry.reset()
```

## Common Patterns

### Pattern: Multiple APIs with Different Limits

```python
def setup_multi_api_limiters():
    """Setup limiters for different API providers."""

    # OpenAI - conservative
    LimiterRegistry.register(
        "openai",
        max_concurrent=5,
        max_per_window=60
    )

    # Anthropic - moderate
    LimiterRegistry.register(
        "anthropic",
        max_concurrent=5,
        max_per_window=50
    )

    # Google - aggressive
    LimiterRegistry.register(
        "google",
        max_concurrent=10,
        max_per_window=1500
    )

    # Internal - unlimited concurrent
    LimiterRegistry.register(
        "internal",
        max_concurrent=100,
        max_per_window=None
    )

class MultiProviderNode(AsyncNode):
    async def exec_async(self, _):
        provider = self.params["provider"]
        prompt = self.params["prompt"]

        # Use different limiter based on provider
        async with LimiterRegistry.get(provider):
            if provider == "openai":
                return await call_openai(prompt)
            elif provider == "anthropic":
                return await call_anthropic(prompt)
            elif provider == "google":
                return await call_google(prompt)
```

### Pattern: Tenant-Specific Rate Limiting

```python
def register_tenant_limiters(tenants):
    """Each tenant gets their own rate limiter."""
    for tenant in tenants:
        LimiterRegistry.register(
            f"tenant_{tenant.id}",
            max_concurrent=tenant.max_concurrent,
            max_per_window=tenant.max_per_minute
        )

class TenantNode(AsyncNode):
    async def exec_async(self, _):
        tenant_id = self.params["tenant_id"]

        # Use tenant-specific limiter
        async with LimiterRegistry.get(f"tenant_{tenant_id}"):
            return await process_for_tenant(tenant_id)
```

### Pattern: Environment-Based Configuration

```python
import os

def setup_env_based_limiters():
    """Configure based on environment."""
    env = os.getenv("ENVIRONMENT", "production")

    if env == "development":
        # Relaxed limits for dev
        LimiterRegistry.register("api", max_concurrent=2, max_per_window=10)
    elif env == "staging":
        # Moderate limits for staging
        LimiterRegistry.register("api", max_concurrent=5, max_per_window=50)
    else:  # production
        # Full limits for production
        LimiterRegistry.register("api", max_concurrent=20, max_per_window=200)
```

### Pattern: Lazy Registration in Libraries

```python
class ReusableNode(AsyncNode):
    """Node that can be used in different applications."""

    async def exec_async(self, item):
        # Get or create - works even if not pre-registered
        limiter = LimiterRegistry.get_or_create(
            "my_library_api",
            max_concurrent=10,
            max_per_window=100
        )

        async with limiter:
            return await call_api(item)
```

## Monitoring Shared Usage

```python
async def monitor_limiter_usage():
    """Monitor how a shared limiter is being used."""
    while True:
        stats = LimiterRegistry.stats("openai")

        print(f"OpenAI Limiter:")
        print(f"  Current requests in window: {stats['current_window_count']}")
        print(f"  Max per window: {stats['max_per_window']}")
        print(f"  Utilization: {stats['current_window_count'] / stats['max_per_window'] * 100:.1f}%")

        await asyncio.sleep(10)  # Check every 10 seconds
```

## Testing with Shared Limiters

```python
import pytest

@pytest.fixture(autouse=True)
def reset_limiters():
    """Reset registry before each test."""
    LimiterRegistry.reset()
    yield
    LimiterRegistry.reset()

async def test_shared_limiting():
    # Register test limiter
    LimiterRegistry.register("test_api", max_concurrent=2, max_per_window=10)

    # Your test code
    async with LimiterRegistry.get("test_api"):
        result = await call_test_api()

    # Verify stats
    stats = LimiterRegistry.stats("test_api")
    assert stats['current_window_count'] == 1
```

## Comparison: Shared vs Individual Limiters

### Individual Limiters (Default)
```python
class Node1(ThrottledParallelBatchNode):
    max_concurrent = 10  # Node1's own limit

class Node2(ThrottledParallelBatchNode):
    max_concurrent = 10  # Node2's own limit

# Total possible concurrent: 20 (10 + 10)
```

### Shared Limiter
```python
LimiterRegistry.register("api", max_concurrent=10)

class Node1(AsyncNode):
    async def exec_async(self, item):
        async with LimiterRegistry.get("api"):
            ...

class Node2(AsyncNode):
    async def exec_async(self, item):
        async with LimiterRegistry.get("api"):
            ...

# Total possible concurrent: 10 (shared across both)
```

## Integration with Throttled Nodes

You can use shared limiters inside throttled nodes:

```python
from pocketflow_throttled import ThrottledParallelBatchNode

class HybridNode(ThrottledParallelBatchNode):
    """Node with its own throttling + shared global limit."""

    # Node-level throttling
    max_concurrent = 5
    max_per_minute = 60

    async def exec_async(self, item):
        # Additional global throttling via shared limiter
        async with LimiterRegistry.get("global_api"):
            return await call_api(item)

# Effective limits:
# - Node can run max 5 items concurrently
# - But global API calls across all nodes limited by "global_api" limiter
```

## Common Mistakes

### ❌ Forgetting to Register
```python
# This will raise KeyError
async with LimiterRegistry.get("unregistered"):
    ...

# Fix: Register first or use get_or_create
limiter = LimiterRegistry.get_or_create("api", max_concurrent=10)
```

### ❌ Registering Multiple Times
```python
# Don't do this in loops or multiple times
for i in range(10):
    LimiterRegistry.register("api", ...)  # Wrong!

# Do this: Register once at startup
LimiterRegistry.register("api", ...)
```

### ❌ Not Using Context Manager
```python
# Wrong - limiter never releases
limiter = LimiterRegistry.get("api")
result = await call_api()

# Correct - use async with
async with LimiterRegistry.get("api"):
    result = await call_api()
```

## Best Practices

1. **Register at startup** - Create all limiters during application initialization
2. **Use descriptive names** - "openai_gpt4", "anthropic_claude", etc.
3. **Document shared limiters** - Make it clear which components share which limiters
4. **Monitor usage** - Track limiter statistics in production
5. **Test with reset** - Use `LimiterRegistry.reset()` in test fixtures

## Related Skills

- **Basic**: [Skill 01: Basic Node Throttling](01-basic-node-throttling.md) - Individual limiters
- **Flows**: [Skill 03: Flow-Level Throttling](03-flow-level-throttling.md) - Flow concurrency
- **Nested**: [Skill 07: Nested Throttling](07-nested-throttling.md) - Combine patterns

## When NOT to Use

- **Independent APIs** → Use individual node/flow throttling
- **Single service** → Use node or flow throttling directly
- **Different quotas per component** → Use separate limiters or individual throttling
