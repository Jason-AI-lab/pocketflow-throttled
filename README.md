# PocketFlow Throttled

[![PyPI version](https://badge.fury.io/py/pocketflow-throttled.svg)](https://badge.fury.io/py/pocketflow-throttled)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Rate-limited parallel execution extension for [PocketFlow](https://github.com/The-Pocket/PocketFlow)** — throttle LLM and API calls with ease.

## 🎯 Problem

When using PocketFlow's `AsyncParallelBatchNode` or `AsyncParallelBatchFlow` with LLM APIs:

```python
# ❌ This fires ALL requests simultaneously → 429 errors!
class TranslateNode(AsyncParallelBatchNode):
    async def exec_async(self, text):
        return await call_openai(text)  # 100 requests at once = rate limit
```

## ✅ Solution

Drop-in replacements with automatic rate limiting:

```python
from pocketflow_throttled import ThrottledParallelBatchNode, Presets

class TranslateNode(ThrottledParallelBatchNode):
    max_concurrent = 5      # Max 5 simultaneous requests
    max_per_minute = 60     # Max 60 requests per minute
    
    async def exec_async(self, text):
        return await call_openai(text)  # Automatically throttled!

# Or use presets for popular providers
node = ThrottledParallelBatchNode(**Presets.OPENAI_TIER1)
```

## 📦 Installation

```bash
pip install pocketflow-throttled
```

Or with LLM provider support:

```bash
pip install pocketflow-throttled[anthropic]  # For Anthropic Claude
pip install pocketflow-throttled[openai]     # For OpenAI
pip install pocketflow-throttled[all]        # Both
```

## 🚀 Quick Start

### Basic Node Throttling

```python
import asyncio
from pocketflow import AsyncFlow
from pocketflow_throttled import ThrottledParallelBatchNode

class ProcessItemsNode(ThrottledParallelBatchNode):
    max_concurrent = 5      # Max 5 simultaneous operations
    max_per_minute = 60     # Rate limit: 60 per minute
    
    async def prep_async(self, shared):
        return shared["items"]
    
    async def exec_async(self, item):
        # Your API call here - automatically throttled!
        return await some_api_call(item)
    
    async def post_async(self, shared, prep_res, exec_res_list):
        shared["results"] = exec_res_list
        return "default"

# Run it
async def main():
    flow = AsyncFlow(start=ProcessItemsNode())
    shared = {"items": list(range(100))}
    await flow.run_async(shared)
    print(f"Processed {len(shared['results'])} items!")

asyncio.run(main())
```

### Flow-Level Throttling

For batch processing where each item requires multiple API calls:

```python
from pocketflow import AsyncNode
from pocketflow_throttled import ThrottledAsyncParallelBatchFlow

class FetchUserDataNode(AsyncNode):
    async def exec_async(self, _):
        user_id = self.params["user_id"]
        return await fetch_user(user_id)

class ProcessUsersFlow(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = 10  # Process 10 users concurrently
    max_flows_per_minute = 60  # Start max 60 users per minute
    
    async def prep_async(self, shared):
        return [{"user_id": uid} for uid in shared["user_ids"]]

# Process 1000 users, 10 at a time
flow = ProcessUsersFlow(start=FetchUserDataNode())
await flow.run_async({"user_ids": range(1000)})
```

### Using Presets

```python
from pocketflow_throttled import ThrottledParallelBatchNode, Presets

# Use pre-configured limits for popular providers
class MyNode(ThrottledParallelBatchNode):
    max_concurrent = Presets.OPENAI_TIER1["max_concurrent"]
    max_per_minute = Presets.OPENAI_TIER1["max_per_minute"]

# Or pass as kwargs
node = ThrottledParallelBatchNode(**Presets.ANTHROPIC_STANDARD)
```

Available presets:
- **OpenAI**: `OPENAI_FREE`, `OPENAI_TIER1` through `OPENAI_TIER5`
- **Anthropic**: `ANTHROPIC_FREE`, `ANTHROPIC_BUILD_TIER1` through `ANTHROPIC_BUILD_TIER4`
- **Google**: `GOOGLE_FREE`, `GOOGLE_PAY_AS_YOU_GO`
- **Generic**: `CONSERVATIVE`, `MODERATE`, `AGGRESSIVE`
- **Scraping**: `SCRAPING_POLITE`, `SCRAPING_MODERATE`, `SCRAPING_AGGRESSIVE`

### Adaptive Throttling

For APIs with unpredictable rate limits:

```python
from pocketflow_throttled import AdaptiveThrottledNode

class SmartNode(AdaptiveThrottledNode):
    initial_concurrent = 10  # Start optimistic
    min_concurrent = 2       # Never go below 2
    max_concurrent = 50      # Cap at 50
    backoff_factor = 0.5     # Halve on rate limit
    recovery_factor = 1.2    # +20% after sustained success
    
    async def exec_async(self, item):
        return await api_call(item)
```

The node automatically:
- **Backs off** when hitting rate limits (reduces concurrency)
- **Recovers** after sustained success (increases concurrency)
- **Self-tunes** to optimal throughput

### Shared Rate Limiters

For global rate limit coordination across nodes and flows:

```python
from pocketflow_throttled import LimiterRegistry

# Register at app startup
LimiterRegistry.register("openai", max_concurrent=10, max_per_window=60)

# Use anywhere in your code
class MyNode(AsyncNode):
    async def exec_async(self, item):
        async with LimiterRegistry.get("openai"):
            return await call_openai(item)
```

## 📚 API Reference

### Node Classes

#### `ThrottledParallelBatchNode`

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_concurrent` | `int` | `5` | Maximum simultaneous executions |
| `max_per_minute` | `int \| None` | `None` | Rate limit (None = unlimited) |
| `max_retries` | `int` | `1` | Retry attempts per item |
| `wait` | `int` | `0` | Seconds between retries |

#### `AdaptiveThrottledNode`

Inherits from `ThrottledParallelBatchNode` plus:

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `initial_concurrent` | `int` | `5` | Starting concurrency |
| `min_concurrent` | `int` | `1` | Floor for backoff |
| `max_concurrent` | `int` | `20` | Ceiling for recovery |
| `backoff_factor` | `float` | `0.5` | Multiplier on rate limit |
| `recovery_threshold` | `int` | `10` | Successes before recovery |
| `recovery_factor` | `float` | `1.2` | Multiplier on recovery |
| `propagate_rate_limit` | `bool` | `False` | Re-raise as `RateLimitHit` |

### Flow Classes

#### `ThrottledAsyncParallelBatchFlow`

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_concurrent_flows` | `int` | `5` | Maximum simultaneous flow instances |
| `max_flows_per_minute` | `int \| None` | `None` | Rate limit (None = unlimited) |

#### `AdaptiveThrottledBatchFlow`

Inherits from `ThrottledAsyncParallelBatchFlow` plus:

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `initial_concurrent_flows` | `int` | `5` | Starting concurrency |
| `min_concurrent_flows` | `int` | `1` | Floor for backoff |
| `max_concurrent_flows` | `int` | `20` | Ceiling for recovery |
| `backoff_factor` | `float` | `0.5` | Multiplier on rate limit |
| `recovery_threshold` | `int` | `10` | Successes before recovery |
| `recovery_factor` | `float` | `1.2` | Multiplier on recovery |

### Utilities

#### `RateLimiter`

Low-level rate limiter with sliding window algorithm:

```python
from pocketflow_throttled import RateLimiter

limiter = RateLimiter(
    max_concurrent=5,      # Semaphore limit
    max_per_window=60,     # Sliding window limit
    window_seconds=60      # Window duration
)

async with limiter:
    await make_api_call()
```

#### `LimiterRegistry`

Global registry for shared rate limiters:

```python
from pocketflow_throttled import LimiterRegistry

# Register
LimiterRegistry.register("api_name", max_concurrent=10)

# Get
limiter = LimiterRegistry.get("api_name")

# Get or create (lazy)
limiter = LimiterRegistry.get_or_create("api_name", max_concurrent=10)

# List all
LimiterRegistry.list_all()  # {'api_name': {...}}

# Reset
LimiterRegistry.reset()  # Clear all
```

#### `RateLimitHit`

Exception for signaling rate limits:

```python
from pocketflow_throttled import RateLimitHit

# Raise in nodes to signal to adaptive flows
raise RateLimitHit("Rate limit exceeded", retry_after=30.0)
```

## 📁 Project Structure

```
pocketflow-throttled/
├── src/pocketflow_throttled/
│   ├── __init__.py          # Package exports
│   ├── rate_limiter.py      # RateLimiter class
│   ├── nodes.py             # Throttled node classes
│   ├── flows.py             # Throttled flow classes
│   ├── shared.py            # LimiterRegistry
│   ├── exceptions.py        # RateLimitHit
│   └── presets.py           # Rate limit presets
├── tests/
│   ├── test_rate_limiter.py
│   ├── test_nodes.py
│   ├── test_flows.py
│   ├── test_shared.py
│   └── test_presets.py
├── cookbook/
│   └── rate_limited_llm_batch/
│       ├── main.py                    # Translation example
│       ├── adaptive_example.py        # Adaptive node demo
│       ├── presets_example.py         # Using presets
│       ├── flow_throttle_example.py   # Flow throttling
│       └── shared_limiter_example.py  # Shared limiters
├── pyproject.toml
└── README.md
```

## 🧪 Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=pocketflow_throttled --cov-report=html
```

## 🔗 Related

- [PocketFlow](https://github.com/The-Pocket/PocketFlow) - The 100-line LLM framework
- [PocketFlow Documentation](https://the-pocket.github.io/PocketFlow/)
- [Parallel Execution Docs](https://the-pocket.github.io/PocketFlow/core_abstraction/parallel.html)

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
