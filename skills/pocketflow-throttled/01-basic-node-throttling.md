---
name: "basic-node-throttling"
description: "Fixed rate limits for single-node batch processing. Use when you know exact API rate limits and need to prevent 429 errors."
---

# Skill 01: Basic Node Throttling

**Difficulty**: Beginner
**Source**: `cookbook/rate_limited_llm_batch/main.py`

## When to Use

- Processing a batch of items through a single API
- You know the exact rate limits for your API
- Want to prevent 429 (too many requests) errors
- Need parallel execution but within fixed limits

## Key Concepts

`ThrottledParallelBatchNode` provides two types of rate limiting:

1. **Concurrency limit** (`max_concurrent`): Maximum simultaneous API calls
2. **Throughput limit** (`max_per_minute`): Maximum calls per minute

Both limits work together to prevent overwhelming the API.

## Core Pattern

```python
from pocketflow_throttled import ThrottledParallelBatchNode
from pocketflow import AsyncFlow

class MyThrottledNode(ThrottledParallelBatchNode):
    # Configure rate limits
    max_concurrent = 5      # Max 5 simultaneous API calls
    max_per_minute = 60     # Max 60 calls per minute

    # Optional retry configuration
    max_retries = 3
    wait = 2  # seconds between retries

    async def prep_async(self, shared):
        """Return list of items to process."""
        return shared["items"]

    async def exec_async(self, item):
        """Process a single item - called once per item with rate limiting."""
        return await call_api(item)

    async def post_async(self, shared, prep_res, exec_res_list):
        """Store results after all items are processed."""
        shared["results"] = exec_res_list
        return "default"

# Use in a flow
flow = AsyncFlow(start=MyThrottledNode())
await flow.run_async({"items": [...]})
```

## Complete Example: Batch Translation

```python
from pocketflow_throttled import ThrottledParallelBatchNode
from pocketflow import AsyncFlow

class TranslateTextNode(ThrottledParallelBatchNode):
    """Translate text into multiple languages with rate limiting."""

    # Match Anthropic's standard tier limits
    max_concurrent = 5
    max_per_minute = 60

    # Retry configuration
    max_retries = 3
    wait = 2

    def __init__(self, provider: str = "anthropic", **kwargs):
        super().__init__(**kwargs)
        self.provider = provider

    async def prep_async(self, shared):
        """Prepare (text, language) pairs for translation."""
        text = shared["text"]
        languages = shared["languages"]
        return [(text, lang) for lang in languages]

    async def exec_async(self, item):
        """Translate text to a single language."""
        text, target_language = item

        prompt = f"Translate to {target_language}: {text}"
        translation = await call_llm(prompt, provider=self.provider)

        return {
            "language": target_language,
            "translation": translation,
        }

    async def post_async(self, shared, prep_res, exec_res_list):
        """Store translations in shared store."""
        shared["translations"] = {
            result["language"]: result["translation"]
            for result in exec_res_list
            if result is not None
        }
        return "default"

# Usage
async def translate_document():
    node = TranslateTextNode(provider="anthropic")
    flow = AsyncFlow(start=node)

    shared = {
        "text": "Hello, how are you?",
        "languages": ["Spanish", "French", "German", "Italian"]
    }

    await flow.run_async(shared)

    # Access results
    for lang, translation in shared["translations"].items():
        print(f"{lang}: {translation}")
```

## How Rate Limiting Works

The node combines two mechanisms:

1. **Semaphore (concurrency)**: Limits simultaneous operations
   - Only N tasks can run at the same time
   - Other tasks wait for an available slot

2. **Sliding Window (throughput)**: Tracks requests over time
   - Maintains timestamps of recent requests
   - Blocks if too many requests in the time window

```python
# Pseudocode of what happens internally
async def exec_async(self, item):
    async with self.limiter:  # Handles both limits
        # 1. Wait if we're at max_concurrent
        # 2. Wait if we've hit max_per_minute in the last 60s
        # 3. Execute when both limits allow
        return await your_exec_async(item)
```

## Configuration Tips

### Conservative Settings
```python
class ConservativeNode(ThrottledParallelBatchNode):
    max_concurrent = 2      # Very safe
    max_per_minute = 30
```

### Moderate Settings
```python
class ModerateNode(ThrottledParallelBatchNode):
    max_concurrent = 5
    max_per_minute = 100
```

### Aggressive Settings
```python
class AggressiveNode(ThrottledParallelBatchNode):
    max_concurrent = 20
    max_per_minute = 500
```

## Performance Comparison

For 100 items with 0.5s API latency each:

| Approach | Time | Errors | Notes |
|----------|------|--------|-------|
| Sequential | ~50s | 0 | Safe but slow |
| Parallel (no throttle) | ~5s | Many 429s | ❌ Don't use |
| **Throttled (max_concurrent=5)** | **~10s** | **0** | ✅ Recommended |
| **Throttled (max_concurrent=10)** | **~5-6s** | **0** | ✅ If API allows |

## Common Mistakes

### ❌ Setting limits too high
```python
# Might exceed API limits
max_concurrent = 100  # Too aggressive for most APIs
```

### ❌ Forgetting to await
```python
# Wrong - missing await
flow.run_async(shared)

# Correct
await flow.run_async(shared)
```

### ❌ Not handling None results
```python
# exec_async can return None on errors
async def post_async(self, shared, prep_res, exec_res_list):
    # Filter out None values
    shared["results"] = [r for r in exec_res_list if r is not None]
```

## Resetting Between Runs

If running the same node multiple times, reset the limiter:

```python
node = MyThrottledNode()

# First run
await node._run_async(shared1)

# Reset before second run
node.reset_limiter()

# Second run
await node._run_async(shared2)
```

## Integration with Regular AsyncFlow

```python
from pocketflow import AsyncNode, AsyncFlow
from pocketflow_throttled import ThrottledParallelBatchNode

# Mix throttled and non-throttled nodes
class PrepareNode(AsyncNode):
    """No throttling needed - just data prep."""
    async def exec_async(self, _):
        return "prepared"

    async def post_async(self, shared, prep_res, exec_res):
        shared["data"] = prep_res
        return "api_call"

class APICallNode(ThrottledParallelBatchNode):
    """Throttled API calls."""
    max_concurrent = 5
    max_per_minute = 60

    async def prep_async(self, shared):
        return shared["items"]

    async def exec_async(self, item):
        return await call_api(item)

# Build flow
prep = PrepareNode()
api = APICallNode()
prep - "api_call" >> api

flow = AsyncFlow(start=prep)
```

## Example Code

See [examples/01-basic-node-throttling.py](examples/01-basic-node-throttling.py) for a complete, runnable example demonstrating basic node throttling with a mock LLM API.

## Related Skills

- **Next**: [Skill 02: Adaptive Throttling](02-adaptive-throttling.md) - Self-tuning rate limits
- **Alternative**: [Skill 06: Using Presets](06-using-presets.md) - Pre-configured limits
- **Advanced**: [Skill 07: Nested Throttling](07-nested-throttling.md) - Flow + node throttling

## When NOT to Use

- **Unknown rate limits** → Use [Adaptive Throttling](02-adaptive-throttling.md)
- **Multi-node pipeline per item** → Use [Flow-Level Throttling](03-flow-level-throttling.md)
- **Shared API across services** → Use [Shared Limiters](04-shared-limiters.md)
