---
name: "pocketflow-throttled"
description: "Rate-limited parallel execution patterns for LLM APIs and web services. Use when you need to prevent 429 errors and optimize throughput."
---

# PocketFlow Throttled

Reusable patterns and skills for working with `pocketflow-throttled`, a library for rate-limited parallel execution of LLM APIs and web services.

## Quick Decision Guide

**Choose the right pattern based on your needs:**

- **Getting 429 errors from LLM API?** → [01-basic-node-throttling.md](01-basic-node-throttling.md)
- **Don't know exact rate limits?** → [02-adaptive-throttling.md](02-adaptive-throttling.md)
- **Each item needs multiple API calls?** → [03-flow-level-throttling.md](03-flow-level-throttling.md)
- **Multiple services calling same API?** → [04-shared-limiters.md](04-shared-limiters.md)
- **Different users need different configs?** → [05-parameterized-flows.md](05-parameterized-flows.md)
- **Using OpenAI/Anthropic/Google?** → [06-using-presets.md](06-using-presets.md)
- **Complex pipeline with many API calls?** → [07-nested-throttling.md](07-nested-throttling.md)

## Available Patterns

### Core Skills

1. **[Basic Node Throttling](01-basic-node-throttling.md)** - Fixed rate limits for single-node batch processing
2. **[Adaptive Throttling](02-adaptive-throttling.md)** - Self-tuning concurrency that adapts to API responses
3. **[Flow-Level Throttling](03-flow-level-throttling.md)** - Controlling concurrent flow instances
4. **[Shared Limiters](04-shared-limiters.md)** - Global rate limiter coordination across components
5. **[Parameterized Flows](05-parameterized-flows.md)** - Passing different parameters to each flow instance
6. **[Using Presets](06-using-presets.md)** - Pre-configured settings for popular APIs
7. **[Nested Throttling](07-nested-throttling.md)** - Combining flow and node-level rate limits
8. **[Architecture Patterns](08-architecture-patterns.md)** - Core design patterns and flow mechanics

## When to Use This Skill

Use `pocketflow-throttled` patterns when you need to:
- Process batches of items through LLM APIs without hitting rate limits
- Maximize throughput while staying within API quotas
- Handle unknown or variable rate limits
- Coordinate rate limiting across multiple services
- Build complex multi-step pipelines with rate-limited APIs

## Complexity Levels

- **Beginner**: Skills 01, 06
- **Intermediate**: Skills 02, 03, 05
- **Advanced**: Skills 04, 07, 08

## Learning Path

1. Start with **Skill 01** - Understand basic throttling
2. Read **Skill 08** - Learn the architecture
3. Try **Skill 02** - Add adaptive behavior
4. Explore **Skill 03** - Scale to flow-level
5. Master **Skills 04, 05, 07** - Advanced patterns

## Additional Resources

- **Source Code**: `/cookbook/rate_limited_llm_batch/`
- **Architecture Docs**: `/docs/`
- **Main Documentation**: `/CLAUDE.md`
