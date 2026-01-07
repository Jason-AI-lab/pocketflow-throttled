# PocketFlow Throttled

[![PyPI version](https://badge.fury.io/py/pocketflow-throttled.svg)](https://badge.fury.io/py/pocketflow-throttled)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Rate-limited parallel execution extension for [PocketFlow](https://github.com/The-Pocket/PocketFlow)** — throttle LLM and API calls with ease.

## 🎯 Problem

When using PocketFlow's `AsyncParallelBatchNode` with LLM APIs:

```python
# ❌ This fires ALL requests simultaneously → 429 errors!
class TranslateNode(AsyncParallelBatchNode):
    async def exec_async(self, text):
        return await call_openai(text)  # 100 requests at once = rate limit
```

## ✅ Solution

Drop-in replacement with automatic rate limiting:

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

### Basic Usage

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

### Using Presets

```python
from pocketflow_throttled import ThrottledParallelBatchNode, Presets

# Use pre-configured limits for popular providers
class MyNode(ThrottledParallelBatchNode):
    # OpenAI Tier 1: 5 concurrent, 60 RPM
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

## 📚 API Reference

### `RateLimiter`

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

### `ThrottledParallelBatchNode`

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_concurrent` | `int` | `5` | Maximum simultaneous executions |
| `max_per_minute` | `int \| None` | `None` | Rate limit (None = unlimited) |
| `max_retries` | `int` | `1` | Retry attempts per item |
| `wait` | `int` | `0` | Seconds between retries |

### `AdaptiveThrottledNode`

Inherits from `ThrottledParallelBatchNode` plus:

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `initial_concurrent` | `int` | `5` | Starting concurrency |
| `min_concurrent` | `int` | `1` | Floor for backoff |
| `max_concurrent` | `int` | `20` | Ceiling for recovery |
| `backoff_factor` | `float` | `0.5` | Multiplier on rate limit |
| `recovery_threshold` | `int` | `10` | Successes before recovery |
| `recovery_factor` | `float` | `1.2` | Multiplier on recovery |

## 📁 Project Structure

```
pocketflow-throttled/
├── src/pocketflow_throttled/
│   ├── __init__.py          # Package exports
│   ├── rate_limiter.py      # RateLimiter class
│   ├── nodes.py             # Throttled node classes
│   └── presets.py           # Rate limit presets
├── tests/
│   ├── test_rate_limiter.py
│   ├── test_nodes.py
│   └── test_presets.py
├── cookbook/
│   └── rate_limited_llm_batch/
│       ├── main.py          # Translation example
│       ├── adaptive_example.py
│       └── presets_example.py
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
