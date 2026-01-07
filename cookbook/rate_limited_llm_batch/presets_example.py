"""
Using Rate Limit Presets
========================

This example shows different ways to use the pre-configured
rate limit presets for popular LLM providers.

Presets are available for:
- OpenAI (Free, Tier 1-5)
- Anthropic (Free, Build Tiers 1-4)
- Google AI (Free, Pay-as-you-go)
- Cohere (Trial, Production)
- Hugging Face (Free, Pro)
- Generic (Conservative, Moderate, Aggressive)
- Web Scraping (Polite, Moderate, Aggressive)
"""

import asyncio
from pocketflow import AsyncFlow
from pocketflow_throttled import (
    ThrottledParallelBatchNode,
    AdaptiveThrottledNode,
    Presets,
    RateLimitConfig,
)


# =============================================================================
# Method 1: Class Attributes
# =============================================================================

class OpenAITier1Node(ThrottledParallelBatchNode):
    """
    Node configured for OpenAI Tier 1 rate limits.
    
    Uses class attributes to set limits.
    """
    max_concurrent = Presets.OPENAI_TIER1["max_concurrent"]  # 5
    max_per_minute = Presets.OPENAI_TIER1["max_per_minute"]  # 60
    
    async def prep_async(self, shared):
        return shared.get("items", [])
    
    async def exec_async(self, item):
        await asyncio.sleep(0.01)  # Simulate API call
        return f"Processed: {item}"
    
    async def post_async(self, shared, prep_res, exec_res_list):
        shared["results"] = exec_res_list
        return "default"


# =============================================================================
# Method 2: Constructor kwargs
# =============================================================================

class GenericNode(ThrottledParallelBatchNode):
    """Generic node that accepts any rate limit config."""
    
    async def prep_async(self, shared):
        return shared.get("items", [])
    
    async def exec_async(self, item):
        await asyncio.sleep(0.01)
        return f"Processed: {item}"
    
    async def post_async(self, shared, prep_res, exec_res_list):
        shared["results"] = exec_res_list
        return "default"


def create_node_with_preset(preset_name: str) -> GenericNode:
    """
    Create a node with a specific preset.
    
    Args:
        preset_name: Name of the preset (e.g., "OPENAI_TIER1", "CONSERVATIVE")
    """
    preset = Presets.get(preset_name)
    return GenericNode(**preset)


# =============================================================================
# Method 3: Using RateLimitConfig objects
# =============================================================================

def demo_rate_limit_config():
    """Show how to use RateLimitConfig for typed configuration."""
    
    # Get a typed config from CONFIGS dict
    config: RateLimitConfig = Presets.CONFIGS["anthropic_tier1"]
    
    print(f"Config: {config}")
    print(f"  Description: {config.description}")
    print(f"  Max Concurrent: {config.max_concurrent}")
    print(f"  Max Per Minute: {config.max_per_minute}")
    
    # Convert to kwargs for node
    node = GenericNode(**config.to_dict())
    return node


# =============================================================================
# List All Available Presets
# =============================================================================

def list_all_presets():
    """Print all available presets with their values."""
    
    print("=" * 60)
    print("Available Rate Limit Presets")
    print("=" * 60)
    
    # Group presets by provider
    providers = {
        "OpenAI": ["OPENAI_FREE", "OPENAI_TIER1", "OPENAI_TIER2", "OPENAI_TIER3", "OPENAI_TIER4", "OPENAI_TIER5"],
        "Anthropic": ["ANTHROPIC_FREE", "ANTHROPIC_BUILD_TIER1", "ANTHROPIC_BUILD_TIER2", "ANTHROPIC_BUILD_TIER3", "ANTHROPIC_BUILD_TIER4"],
        "Google": ["GOOGLE_FREE", "GOOGLE_PAY_AS_YOU_GO"],
        "Cohere": ["COHERE_TRIAL", "COHERE_PRODUCTION"],
        "Hugging Face": ["HUGGINGFACE_FREE", "HUGGINGFACE_PRO"],
        "Mistral": ["MISTRAL_FREE", "MISTRAL_STANDARD"],
        "Generic": ["CONSERVATIVE", "MODERATE", "AGGRESSIVE", "UNLIMITED_CONCURRENT"],
        "Web Scraping": ["SCRAPING_POLITE", "SCRAPING_MODERATE", "SCRAPING_AGGRESSIVE"],
    }
    
    for provider, preset_names in providers.items():
        print(f"\n{provider}:")
        print("-" * 40)
        for name in preset_names:
            if hasattr(Presets, name):
                preset = getattr(Presets, name)
                rpm = preset.get("max_per_minute", "unlimited")
                print(f"  {name:30} | concurrent: {preset['max_concurrent']:3} | RPM: {rpm}")


# =============================================================================
# Demo: Compare Different Presets
# =============================================================================

async def compare_presets():
    """
    Compare performance with different preset configurations.
    """
    import time
    
    print("\n" + "=" * 60)
    print("Preset Performance Comparison")
    print("=" * 60)
    
    presets_to_test = [
        ("CONSERVATIVE", Presets.CONSERVATIVE),
        ("MODERATE", Presets.MODERATE),
        ("AGGRESSIVE", Presets.AGGRESSIVE),
    ]
    
    items = list(range(20))
    
    for name, preset in presets_to_test:
        node = GenericNode(**preset)
        shared = {"items": items.copy()}
        
        start = time.time()
        await node._run_async(shared)
        elapsed = time.time() - start
        
        print(f"\n{name}:")
        print(f"  Config: {preset}")
        print(f"  Items: {len(items)}")
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Rate: {len(items)/elapsed:.1f} items/sec")


# =============================================================================
# Main
# =============================================================================

async def main():
    # List all presets
    list_all_presets()
    
    # Demo typed config
    print("\n" + "=" * 60)
    print("Using RateLimitConfig")
    print("=" * 60)
    demo_rate_limit_config()
    
    # Compare presets
    await compare_presets()
    
    print("\n" + "=" * 60)
    print("Usage Examples")
    print("=" * 60)
    print("""
# Method 1: Class attributes
class MyNode(ThrottledParallelBatchNode):
    max_concurrent = Presets.OPENAI_TIER1["max_concurrent"]
    max_per_minute = Presets.OPENAI_TIER1["max_per_minute"]

# Method 2: Constructor kwargs
node = ThrottledParallelBatchNode(**Presets.ANTHROPIC_STANDARD)

# Method 3: Using Presets.get()
node = ThrottledParallelBatchNode(**Presets.get("openai_tier1"))

# Method 4: Using RateLimitConfig
config = Presets.CONFIGS["conservative"]
node = ThrottledParallelBatchNode(**config.to_dict())
""")


if __name__ == "__main__":
    asyncio.run(main())
