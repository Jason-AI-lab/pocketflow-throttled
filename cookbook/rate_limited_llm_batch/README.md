# Rate-Limited LLM Batch Processing

This cookbook demonstrates how to use `pocketflow-throttled` for batch processing
with LLM APIs while respecting rate limits.

## Problem

When processing large batches of data with LLM APIs:
- **Without throttling**: Requests fire simultaneously, triggering 429 errors
- **Sequential processing**: Works but is painfully slow
- **Manual rate limiting**: Complex and error-prone

## Solution

`ThrottledParallelBatchNode` provides the best of both worlds:
- **Concurrent execution** for speed
- **Automatic rate limiting** to avoid 429 errors
- **Simple configuration** via class attributes or presets

## Examples

### 1. Basic Batch Translation (`main.py`)

Translates a document into multiple languages with rate limiting.

```bash
# Set your API key
export ANTHROPIC_API_KEY="your-key-here"

# Run the example
python main.py
```

### 2. Adaptive Throttling (`adaptive_example.py`)

Shows how `AdaptiveThrottledNode` automatically adjusts throughput based on
API responses - backing off on rate limits and recovering when successful.

### 3. Using Presets (`presets_example.py`)

Demonstrates using pre-configured rate limits for popular LLM providers.

## Key Concepts

### Configuration Options

```python
class MyNode(ThrottledParallelBatchNode):
    max_concurrent = 5      # Max simultaneous requests
    max_per_minute = 60     # Rate limit (requests per minute)
```

### With Presets

```python
from pocketflow_throttled import Presets

node = ThrottledParallelBatchNode(**Presets.ANTHROPIC_STANDARD)
```

### Adaptive Throttling

```python
class MyNode(AdaptiveThrottledNode):
    initial_concurrent = 10  # Start optimistic
    min_concurrent = 2       # Never go below 2
    max_concurrent = 50      # Cap at 50
    backoff_factor = 0.5     # Halve on rate limit
    recovery_factor = 1.2    # +20% after sustained success
```

## Performance Comparison

| Approach | 100 Items | Rate Limit Errors |
|----------|-----------|-------------------|
| Sequential | ~100s | None |
| Parallel (no throttle) | ~10s | Many 429s |
| **Throttled Parallel** | ~20s | None |

## Files

- `main.py` - Main example with batch translation
- `adaptive_example.py` - Adaptive throttling demo
- `presets_example.py` - Using rate limit presets
- `utils.py` - LLM API wrapper utilities
- `requirements.txt` - Dependencies

## Requirements

```
pocketflow>=0.0.3
pocketflow-throttled>=0.1.0
anthropic>=0.18.0  # or your LLM provider
python-dotenv>=1.0.0
```
