# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PocketFlow Throttled is a Python library extending [PocketFlow](https://github.com/The-Pocket/PocketFlow) with rate-limited parallel execution for LLM APIs and web services. It solves 429 (too many requests) errors when using PocketFlow's parallel batch processing.

## Commands

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run tests with coverage
pytest --cov=pocketflow_throttled --cov-report=html

# Run a single test file
pytest tests/test_nodes.py

# Run a specific test
pytest tests/test_nodes.py::test_throttled_node_basic -v

# Type checking
mypy src/

# Linting
ruff check src/

# Auto-format
ruff format src/
```

## Architecture

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

### Key Source Files

- **rate_limiter.py**: Core `RateLimiter` class using async semaphore + sliding window algorithm. Uses deque to track timestamps within a window.
- **nodes.py**: `ThrottledParallelBatchNode` (fixed limits) and `AdaptiveThrottledNode` (self-tuning). Both inherit from PocketFlow's `AsyncNode` and `BatchNode`.
- **flows.py**: `ThrottledAsyncParallelBatchFlow` (fixed) and `AdaptiveThrottledBatchFlow` (adaptive) for flow-level throttling.
- **shared.py**: `LimiterRegistry` singleton for sharing rate limiters across components.
- **exceptions.py**: `RateLimitHit` exception for propagating rate limit events from nodes to flows.
- **presets.py**: Pre-configured `Presets` and `FlowPresets` for OpenAI, Anthropic, Google, and generic use cases.

### Design Patterns

1. **Lazy limiter initialization**: `limiter` properties are created on first access, not in `__init__`. Call `reset_limiter()` between runs.

2. **Two-mode throttling**: Combines semaphore-based concurrency control with sliding window throughput limiting to prevent both overload and burst patterns.

3. **Adaptive state machine**: AdaptiveThrottled classes track consecutive successes and adjust concurrency via `backoff_factor` (on rate limit) and `recovery_factor` (after `recovery_threshold` successes).

4. **Node-to-flow signaling**: Nodes can raise `RateLimitHit` (when `propagate_rate_limit=True`) to trigger flow-level adaptation.

5. **Override pattern**: Custom rate limit detection via `is_rate_limit_error()` method override.

### Important Implementation Details

- `AdaptiveThrottledNode` overrides the `limiter` property to use dynamic `_current_concurrent` instead of static `max_concurrent`
- Flows use `return_exceptions=True` in `asyncio.gather` to avoid cascading failures
- All async state updates use `asyncio.Lock` for thread-safety
- Monotonic time is used to avoid clock drift issues

## Cookbook Examples

Located in `cookbook/rate_limited_llm_batch/`:
- `main.py`: Basic translation example with `ThrottledParallelBatchNode`
- `adaptive_example.py`: Dynamic rate limit tuning demonstration
- `flow_throttle_example.py`: Flow-level concurrency control
- `shared_limiter_example.py`: Cross-node rate limit coordination with `LimiterRegistry`
- `parameterized_flow_example.py`: Passing parameters to flow instances
