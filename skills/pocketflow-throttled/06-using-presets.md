---
name: "using-presets"
description: "Pre-configured settings for popular APIs (OpenAI, Anthropic, Google). Use for quick setup with known API providers."
---

# Skill 06: Using Presets

**Difficulty**: Beginner
**Source**: `pocketflow_throttled/presets.py`

## When to Use

- Using OpenAI, Anthropic, Google, or other popular LLM APIs
- Want to match official rate limit tiers
- Need quick setup without researching limits
- Starting a new project and want reasonable defaults

## Key Concepts

Presets provide pre-configured rate limit settings for:

1. **Provider-specific** - Match official API tiers (OpenAI Tier 1, Anthropic Build Tier 2, etc.)
2. **Generic** - Conservative, Moderate, Aggressive settings
3. **Use-case specific** - Batch processing, real-time, data pipeline
4. **Adaptive** - Starting points for adaptive throttling

## Core Pattern

```python
from pocketflow_throttled import ThrottledParallelBatchNode, Presets

# Method 1: Class attributes
class MyNode(ThrottledParallelBatchNode):
    max_concurrent = Presets.OPENAI_TIER1["max_concurrent"]
    max_per_minute = Presets.OPENAI_TIER1["max_per_minute"]

# Method 2: Constructor kwargs
node = ThrottledParallelBatchNode(**Presets.ANTHROPIC_STANDARD)

# Method 3: Using Presets.get() by name
node = ThrottledParallelBatchNode(**Presets.get("openai_tier1"))
```

## Available Node Presets

### OpenAI Presets

```python
from pocketflow_throttled import Presets

# Free Tier
Presets.OPENAI_FREE
# {'max_concurrent': 3, 'max_per_minute': 20}

# Tier 1 (Default)
Presets.OPENAI_TIER1
# {'max_concurrent': 5, 'max_per_minute': 60}

# Tier 2
Presets.OPENAI_TIER2
# {'max_concurrent': 10, 'max_per_minute': 500}

# Tier 3
Presets.OPENAI_TIER3
# {'max_concurrent': 20, 'max_per_minute': 2000}

# Tier 4
Presets.OPENAI_TIER4
# {'max_concurrent': 50, 'max_per_minute': 5000}

# Tier 5 (Enterprise)
Presets.OPENAI_TIER5
# {'max_concurrent': 100, 'max_per_minute': 10000}
```

### Anthropic Presets

```python
# Free Tier
Presets.ANTHROPIC_FREE
# {'max_concurrent': 2, 'max_per_minute': 5}

# Build Tier 1
Presets.ANTHROPIC_BUILD_TIER1
# {'max_concurrent': 5, 'max_per_minute': 50}

# Build Tier 2
Presets.ANTHROPIC_BUILD_TIER2
# {'max_concurrent': 10, 'max_per_minute': 1000}

# Build Tier 3
Presets.ANTHROPIC_BUILD_TIER3
# {'max_concurrent': 20, 'max_per_minute': 2000}

# Build Tier 4 (Enterprise)
Presets.ANTHROPIC_BUILD_TIER4
# {'max_concurrent': 50, 'max_per_minute': 4000}

# Alias: Standard (same as Build Tier 1)
Presets.ANTHROPIC_STANDARD
```

### Google AI Presets

```python
# Free Tier
Presets.GOOGLE_FREE
# {'max_concurrent': 5, 'max_per_minute': 60}

# Pay-as-you-go
Presets.GOOGLE_PAY_AS_YOU_GO
# {'max_concurrent': 10, 'max_per_minute': 1500}
```

### Other Provider Presets

```python
# Cohere
Presets.COHERE_TRIAL          # {'max_concurrent': 1, 'max_per_minute': 20}
Presets.COHERE_PRODUCTION     # {'max_concurrent': 10, 'max_per_minute': 10000}

# HuggingFace
Presets.HUGGINGFACE_FREE      # {'max_concurrent': 1, 'max_per_minute': 30}
Presets.HUGGINGFACE_PRO       # {'max_concurrent': 10, 'max_per_minute': 300}

# Mistral
Presets.MISTRAL_FREE          # {'max_concurrent': 2, 'max_per_minute': 5}
Presets.MISTRAL_STANDARD      # {'max_concurrent': 5, 'max_per_minute': 60}
```

### Generic Presets

```python
# Conservative - Very safe
Presets.CONSERVATIVE
# {'max_concurrent': 3, 'max_per_minute': 30}

# Moderate - Balanced
Presets.MODERATE
# {'max_concurrent': 10, 'max_per_minute': 100}

# Aggressive - High throughput
Presets.AGGRESSIVE
# {'max_concurrent': 30, 'max_per_minute': 500}

# Unlimited concurrent (throughput limit only)
Presets.UNLIMITED_CONCURRENT
# {'max_concurrent': 1000, 'max_per_minute': 100}
```

### Web Scraping Presets

```python
# Polite - Respectful scraping
Presets.SCRAPING_POLITE
# {'max_concurrent': 1, 'max_per_minute': 10}

# Moderate - Balanced scraping
Presets.SCRAPING_MODERATE
# {'max_concurrent': 3, 'max_per_minute': 30}

# Aggressive - Fast scraping
Presets.SCRAPING_AGGRESSIVE
# {'max_concurrent': 10, 'max_per_minute': 120}
```

## Flow Presets

```python
from pocketflow_throttled import FlowPresets, ThrottledAsyncParallelBatchFlow

# Generic flow presets
class MyFlow(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = FlowPresets.MODERATE["max_concurrent_flows"]
    max_flows_per_minute = FlowPresets.MODERATE["max_flows_per_minute"]

# Or use kwargs
flow = ThrottledAsyncParallelBatchFlow(
    start=node,
    **FlowPresets.BATCH_PROCESSING
)
```

### Available Flow Presets

```python
# Generic
FlowPresets.CONSERVATIVE      # 5 flows, 30/min
FlowPresets.MODERATE          # 10 flows, 60/min
FlowPresets.AGGRESSIVE        # 20 flows, 120/min
FlowPresets.HIGH_THROUGHPUT   # 30 flows, 200/min

# Use-case specific
FlowPresets.BATCH_PROCESSING  # 15 flows, 100/min
FlowPresets.DATA_PIPELINE     # 10 flows, 50/min
FlowPresets.REALTIME          # 5 flows, 300/min
FlowPresets.HEAVY_PROCESSING  # 3 flows, 20/min

# Adaptive flow presets (for AdaptiveThrottledBatchFlow)
FlowPresets.ADAPTIVE_CONSERVATIVE  # initial: 5, min: 2, max: 15
FlowPresets.ADAPTIVE_MODERATE      # initial: 10, min: 3, max: 30
FlowPresets.ADAPTIVE_AGGRESSIVE    # initial: 20, min: 5, max: 50
```

## Usage Examples

### Example: OpenAI Translation Service

```python
from pocketflow_throttled import ThrottledParallelBatchNode, Presets
from pocketflow import AsyncFlow

class OpenAITranslationNode(ThrottledParallelBatchNode):
    """Use OpenAI Tier 1 limits."""

    # Method 1: Direct attribute assignment
    max_concurrent = Presets.OPENAI_TIER1["max_concurrent"]  # 5
    max_per_minute = Presets.OPENAI_TIER1["max_per_minute"]  # 60

    async def exec_async(self, text):
        return await openai.translate(text)

# Usage
node = OpenAITranslationNode()
flow = AsyncFlow(start=node)
```

### Example: Anthropic with Constructor

```python
from pocketflow_throttled import ThrottledParallelBatchNode, Presets

class GenericNode(ThrottledParallelBatchNode):
    async def exec_async(self, item):
        return await process(item)

# Create with Anthropic preset
node = GenericNode(**Presets.ANTHROPIC_BUILD_TIER2)

# node.max_concurrent = 10
# node.max_per_minute = 1000
```

### Example: Generic Conservative Start

```python
from pocketflow_throttled import ThrottledParallelBatchNode, Presets

class SafeNode(ThrottledParallelBatchNode):
    """Start conservative, can adjust later."""

    max_concurrent = Presets.CONSERVATIVE["max_concurrent"]  # 3
    max_per_minute = Presets.CONSERVATIVE["max_per_minute"]  # 30

    async def exec_async(self, item):
        return await unknown_api_call(item)
```

### Example: Web Scraping

```python
from pocketflow_throttled import ThrottledParallelBatchNode, Presets

class PoliteScraperNode(ThrottledParallelBatchNode):
    """Respectful web scraping."""

    max_concurrent = Presets.SCRAPING_POLITE["max_concurrent"]  # 1
    max_per_minute = Presets.SCRAPING_POLITE["max_per_minute"]  # 10

    async def exec_async(self, url):
        return await fetch_url(url)
```

### Example: Flow with Preset

```python
from pocketflow_throttled import ThrottledAsyncParallelBatchFlow, FlowPresets

class BatchProcessingFlow(ThrottledAsyncParallelBatchFlow):
    """Optimized for batch processing workloads."""

    # Use batch processing preset
    max_concurrent_flows = FlowPresets.BATCH_PROCESSING["max_concurrent_flows"]  # 15
    max_flows_per_minute = FlowPresets.BATCH_PROCESSING["max_flows_per_minute"]  # 100

    async def prep_async(self, shared):
        return [{"item": i} for i in shared["items"]]
```

## Advanced: Using RateLimitConfig

```python
from pocketflow_throttled import Presets, ThrottledParallelBatchNode

# Get typed config object
config = Presets.CONFIGS["openai_tier1"]

print(config.description)      # "OpenAI API - Tier 1 (default)"
print(config.max_concurrent)   # 5
print(config.max_per_minute)   # 60
print(config.provider)         # "OpenAI"

# Convert to dict for node
node = ThrottledParallelBatchNode(**config.to_dict())
```

## Listing Available Presets

```python
from pocketflow_throttled import Presets

# Get all preset names
names = Presets.list_all()
# Returns: ["OPENAI_FREE", "OPENAI_TIER1", ..., "CONSERVATIVE", ...]

# Get config by name (case-insensitive)
config = Presets.get("openai_tier1")  # Same as Presets.OPENAI_TIER1

# Check available configs
for name, config in Presets.CONFIGS.items():
    print(f"{name}: {config.description}")
```

## Customizing Presets

### Start with Preset, Adjust as Needed

```python
class CustomNode(ThrottledParallelBatchNode):
    """Start with preset, then customize."""

    # Start with OpenAI Tier 1
    max_concurrent = Presets.OPENAI_TIER1["max_concurrent"]  # 5

    # But use custom per-minute limit
    max_per_minute = 100  # Higher than preset's 60

    async def exec_async(self, item):
        return await process(item)
```

### Create Custom Preset Dictionary

```python
# Define your own preset
MY_CUSTOM_PRESET = {
    "max_concurrent": 7,
    "max_per_minute": 150
}

# Use it
class MyNode(ThrottledParallelBatchNode):
    max_concurrent = MY_CUSTOM_PRESET["max_concurrent"]
    max_per_minute = MY_CUSTOM_PRESET["max_per_minute"]

# Or with constructor
node = ThrottledParallelBatchNode(**MY_CUSTOM_PRESET)
```

## Preset Selection Guide

### By Provider

```python
# OpenAI
if using_openai:
    preset = Presets.OPENAI_TIER1  # Check your actual tier

# Anthropic
if using_anthropic:
    preset = Presets.ANTHROPIC_BUILD_TIER1  # Check your actual tier

# Google
if using_google:
    preset = Presets.GOOGLE_FREE or Presets.GOOGLE_PAY_AS_YOU_GO
```

### By Use Case

```python
# Don't know the API limits
preset = Presets.CONSERVATIVE  # Safe starting point

# Batch processing many items
preset = Presets.MODERATE  # Balanced

# High-throughput requirements
preset = Presets.AGGRESSIVE  # Fast but riskier

# Web scraping
preset = Presets.SCRAPING_POLITE  # Respectful
```

### By Risk Tolerance

```python
# Very risk-averse (avoid any rate limit errors)
preset = Presets.CONSERVATIVE

# Balanced (some risk acceptable)
preset = Presets.MODERATE

# Maximize speed (will hit rate limits, relies on retry)
preset = Presets.AGGRESSIVE
```

## Adaptive Throttling with Preset Start

```python
from pocketflow_throttled import AdaptiveThrottledNode, Presets

class SmartNode(AdaptiveThrottledNode):
    """Start with preset, then adapt."""

    # Use OpenAI Tier 1 as starting point
    initial_concurrent = Presets.OPENAI_TIER1["max_concurrent"]  # 5

    # But allow adaptation
    min_concurrent = 2
    max_concurrent = Presets.OPENAI_TIER5["max_concurrent"]  # 100 (if we get upgraded)

    backoff_factor = 0.5
    recovery_threshold = 10
    recovery_factor = 1.2

    # Also use preset's per-minute limit as safety net
    max_per_minute = Presets.OPENAI_TIER1["max_per_minute"]  # 60
```

## Environment-Based Preset Selection

```python
import os
from pocketflow_throttled import Presets, ThrottledParallelBatchNode

def get_preset_for_env():
    """Select preset based on environment."""
    env = os.getenv("ENVIRONMENT", "production")

    if env == "development":
        return Presets.CONSERVATIVE  # Safe for dev
    elif env == "staging":
        return Presets.MODERATE      # Test realistic loads
    else:  # production
        return Presets.AGGRESSIVE    # Maximize throughput

class EnvironmentAwareNode(ThrottledParallelBatchNode):
    def __init__(self):
        preset = get_preset_for_env()
        super().__init__(**preset)
```

## Common Patterns

### Pattern: Multi-Provider Support

```python
class MultiProviderNode(ThrottledParallelBatchNode):
    def __init__(self, provider: str):
        # Select preset based on provider
        presets_map = {
            "openai": Presets.OPENAI_TIER1,
            "anthropic": Presets.ANTHROPIC_STANDARD,
            "google": Presets.GOOGLE_FREE,
        }

        preset = presets_map.get(provider, Presets.CONSERVATIVE)
        super().__init__(**preset)
        self.provider = provider
```

### Pattern: Tier-Based Node Factory

```python
def create_openai_node(tier: int):
    """Create node configured for specific OpenAI tier."""
    presets = [
        Presets.OPENAI_FREE,
        Presets.OPENAI_TIER1,
        Presets.OPENAI_TIER2,
        Presets.OPENAI_TIER3,
        Presets.OPENAI_TIER4,
        Presets.OPENAI_TIER5,
    ]

    preset = presets[tier] if tier < len(presets) else Presets.OPENAI_TIER5

    return ThrottledParallelBatchNode(**preset)

# Usage
node = create_openai_node(tier=2)  # Tier 2 limits
```

## Related Skills

- **Basic Usage**: [Skill 01: Basic Node Throttling](01-basic-node-throttling.md) - How to use the presets
- **Adaptive**: [Skill 02: Adaptive Throttling](02-adaptive-throttling.md) - Use presets as starting point
- **Flows**: [Skill 03: Flow-Level Throttling](03-flow-level-throttling.md) - Flow presets

## When NOT to Use

- **Known custom limits** → Define your own limits
- **Need exact optimization** → Benchmark and tune manually
- **Limits don't match presets** → Use custom configuration
