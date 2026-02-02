# PocketFlow Throttled Skills for LLMs

This directory contains reusable patterns and skills for working with `pocketflow-throttled`, a library for rate-limited parallel execution of LLM APIs and web services.

## Skill Index

### Core Skills

1. **[Basic Node Throttling](01-basic-node-throttling.md)** - Fixed rate limits for single-node batch processing
2. **[Adaptive Throttling](02-adaptive-throttling.md)** - Self-tuning concurrency that adapts to API responses
3. **[Flow-Level Throttling](03-flow-level-throttling.md)** - Controlling concurrent flow instances
4. **[Shared Limiters](04-shared-limiters.md)** - Global rate limiter coordination across components
5. **[Parameterized Flows](05-parameterized-flows.md)** - Passing different parameters to each flow instance
6. **[Using Presets](06-using-presets.md)** - Pre-configured settings for popular APIs
7. **[Nested Throttling](07-nested-throttling.md)** - Combining flow and node-level rate limits
8. **[Architecture Patterns](08-architecture-patterns.md)** - Core design patterns and flow mechanics

## Quick Decision Guide

### When to Use Each Pattern

```
┌─ Single node processing items? ─────────────┐
│  ✓ ThrottledParallelBatchNode              │
│  → Skill 01: Basic Node Throttling         │
└─────────────────────────────────────────────┘

┌─ Unknown/changing rate limits? ─────────────┐
│  ✓ AdaptiveThrottledNode                   │
│  → Skill 02: Adaptive Throttling           │
└─────────────────────────────────────────────┘

┌─ Multi-node flow per item? ─────────────────┐
│  ✓ ThrottledAsyncParallelBatchFlow         │
│  → Skill 03: Flow-Level Throttling         │
└─────────────────────────────────────────────┘

┌─ Multiple components sharing API? ──────────┐
│  ✓ LimiterRegistry                         │
│  → Skill 04: Shared Limiters               │
└─────────────────────────────────────────────┘

┌─ Different config per item? ────────────────┐
│  ✓ Parameterized prep_async()              │
│  → Skill 05: Parameterized Flows           │
└─────────────────────────────────────────────┘

┌─ Using OpenAI/Anthropic/Google? ────────────┐
│  ✓ Presets (e.g., Presets.OPENAI_TIER1)   │
│  → Skill 06: Using Presets                 │
└─────────────────────────────────────────────┘

┌─ Multiple API calls per item? ──────────────┐
│  ✓ Nested (Flow + Node) throttling         │
│  → Skill 07: Nested Throttling             │
└─────────────────────────────────────────────┘
```

## Problem → Solution Mapping

| Problem | Recommended Skill | Why |
|---------|------------------|-----|
| Getting 429 errors from LLM API | Skill 01 | Add basic rate limiting |
| Don't know exact rate limits | Skill 02 | Adaptive throttling auto-tunes |
| Each item needs multiple API calls | Skill 03 or 07 | Flow or nested throttling |
| Multiple services calling same API | Skill 04 | Shared global limiter |
| Different users need different configs | Skill 05 | Parameterized flows |
| Want to use OpenAI/Anthropic presets | Skill 06 | Pre-configured settings |
| Complex pipeline with many API calls | Skill 07 + 08 | Nested + architecture |

## Complexity Levels

- **Beginner**: Skills 01, 06
- **Intermediate**: Skills 02, 03, 05
- **Advanced**: Skills 04, 07, 08

## Integration Examples

### Simple Translation Service
```python
# Use: Skill 01 + Skill 06
from pocketflow_throttled import ThrottledParallelBatchNode, Presets

class TranslateNode(ThrottledParallelBatchNode):
    max_concurrent = Presets.OPENAI_TIER1["max_concurrent"]
    max_per_minute = Presets.OPENAI_TIER1["max_per_minute"]

    async def exec_async(self, text):
        return await call_llm(f"Translate: {text}")
```

### Adaptive User Processing
```python
# Use: Skill 02 + Skill 05
from pocketflow_throttled import AdaptiveThrottledBatchFlow

class UserFlow(AdaptiveThrottledBatchFlow):
    initial_concurrent_flows = 10

    async def prep_async(self, shared):
        return [{"user_id": uid} for uid in shared["user_ids"]]
```

### Multi-Service Coordination
```python
# Use: Skill 04
from pocketflow_throttled import LimiterRegistry

# Register once at startup
LimiterRegistry.register("openai", max_concurrent=10, max_per_window=60)

# Use anywhere
async with LimiterRegistry.get("openai"):
    result = await call_openai()
```

## Learning Path

1. **Start with Skill 01** - Understand basic throttling
2. **Read Skill 08** - Learn the architecture
3. **Try Skill 02** - Add adaptive behavior
4. **Explore Skill 03** - Scale to flow-level
5. **Master Skills 04, 05, 07** - Advanced patterns

## Common Patterns

### Pattern: Rate-Limited Batch Translation
Skills: 01, 06
Use case: Translate 1000 texts without hitting API limits

### Pattern: Multi-User Pipeline
Skills: 03, 05
Use case: Process many users through multi-step workflow

### Pattern: Self-Tuning API Caller
Skills: 02
Use case: Unknown or variable rate limits

### Pattern: Cross-Service Coordination
Skills: 04
Use case: Multiple nodes sharing same API quota

### Pattern: Complex Data Pipeline
Skills: 07, 08
Use case: Multi-stage processing with various APIs

## Additional Resources

- **Source Code**: `/cookbook/rate_limited_llm_batch/`
- **Architecture Docs**: `/docs/`
- **Main Documentation**: `/CLAUDE.md`

## Contributing New Skills

When adding new skills:
1. Follow the numbering convention
2. Include "When to Use", "Key Concepts", "Code Pattern", and "Example"
3. Add to this README's index
4. Cross-reference related skills
