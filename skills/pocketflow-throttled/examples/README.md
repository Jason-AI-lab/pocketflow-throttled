# PocketFlow Throttled Examples

This directory contains working code examples demonstrating each throttling pattern.

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### Running Examples

Each example is a standalone Python script demonstrating a specific throttling pattern:

```bash
# Basic node throttling
python 01-basic-node-throttling.py

# Adaptive throttling
python 02-adaptive-throttling.py

# Flow-level throttling
python 03-flow-level-throttling.py

# Shared limiters
python 04-shared-limiters.py

# Parameterized flows
python 05-parameterized-flows.py

# Using presets
python 06-using-presets.py
```

## Examples Overview

| Example | Skill | Description |
|---------|-------|-------------|
| [01-basic-node-throttling.py](01-basic-node-throttling.py) | [Skill 01](../01-basic-node-throttling.md) | Fixed rate limits for single-node batch processing |
| [02-adaptive-throttling.py](02-adaptive-throttling.py) | [Skill 02](../02-adaptive-throttling.md) | Self-tuning concurrency that adapts to API responses |
| [03-flow-level-throttling.py](03-flow-level-throttling.py) | [Skill 03](../03-flow-level-throttling.md) | Control concurrent flow instances for multi-node pipelines |
| [04-shared-limiters.py](04-shared-limiters.py) | [Skill 04](../04-shared-limiters.md) | Global rate limiter coordination across components |
| [05-parameterized-flows.py](05-parameterized-flows.py) | [Skill 05](../05-parameterized-flows.md) | Pass different parameters to each flow instance |
| [06-using-presets.py](06-using-presets.py) | [Skill 06](../06-using-presets.md) | Pre-configured settings for popular APIs |

## Shared Utilities

- **[utils.py](utils.py)** - Mock LLM API simulator for testing without real API calls
- **[requirements.txt](requirements.txt)** - Python dependencies

## What These Examples Demonstrate

### Example 01: Basic Node Throttling
- Using `ThrottledParallelBatchNode`
- Setting `max_concurrent` and `max_per_minute`
- Processing batches with fixed rate limits
- Preventing 429 errors

### Example 02: Adaptive Throttling
- Using `AdaptiveThrottledNode`
- Automatic concurrency adjustment
- Backoff on rate limit detection
- Recovery after sustained success

### Example 03: Flow-Level Throttling
- Using `ThrottledAsyncParallelBatchFlow`
- Limiting concurrent flow instances
- Multi-node pipelines per item
- Parameter passing to flow instances

### Example 04: Shared Limiters
- Using `LimiterRegistry`
- Global rate limiter coordination
- Multiple components sharing API quota
- Cross-service rate limiting

### Example 05: Parameterized Flows
- Passing different parameters per flow instance
- Heterogeneous batch processing
- User-specific configurations
- Dynamic parameter selection

### Example 06: Using Presets
- Pre-configured settings for popular APIs
- OpenAI, Anthropic, Google presets
- Quick setup without manual configuration
- Environment-based preset selection

## Mock API Simulator

All examples use the mock LLM API from `utils.py`:

```python
from utils import call_mock_llm

# Simulates API calls with configurable:
# - Latency (default 0.1s)
# - Success rate (default 95%)
# - Rate limit threshold (default 10 req/sec)
result = await call_mock_llm("Your prompt here")
```

This allows you to:
- Test throttling patterns without real API costs
- Simulate rate limit scenarios
- Experiment with different configurations
- Learn the patterns safely

## Customizing for Real APIs

To adapt examples for real APIs:

1. **Replace mock calls** with real API client:
   ```python
   # Change from:
   from utils import call_mock_llm
   result = await call_mock_llm(prompt)
   
   # To:
   import anthropic
   client = anthropic.AsyncAnthropic()
   result = await client.messages.create(...)
   ```

2. **Adjust rate limits** to match your API tier:
   ```python
   # Use presets for known APIs
   from pocketflow_throttled import Presets
   max_concurrent = Presets.ANTHROPIC_BUILD_TIER2["max_concurrent"]
   max_per_minute = Presets.ANTHROPIC_BUILD_TIER2["max_per_minute"]
   ```

3. **Customize rate limit detection** if needed:
   ```python
   class MyAdaptiveNode(AdaptiveThrottledNode):
       def is_rate_limit_error(self, error: Exception) -> bool:
           # Custom detection logic
           return error.status_code == 429
   ```

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError: No module named 'pocketflow_throttled'`:

```bash
# Install from parent directory
cd ../../../
pip install -e .
```

### Rate Limit Simulation

To test rate limit handling, modify `utils.py`:

```python
# Reduce rate limit threshold to trigger more easily
RATE_LIMIT_THRESHOLD = 5  # Lower = more rate limits
```

## Next Steps

1. **Run the examples** to see throttling in action
2. **Read the corresponding skill docs** for detailed explanations
3. **Modify the examples** to match your use case
4. **Integrate into your project** using the patterns learned

## Related Resources

- **Main Skill Documentation**: [../SKILL.md](../SKILL.md)
- **Original Cookbook**: `../../cookbook/rate_limited_llm_batch/`
- **Library Documentation**: `../../../README.md`
