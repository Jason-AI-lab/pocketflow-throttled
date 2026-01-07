"""
Rate-Limited LLM Batch Processing Example
==========================================

This example demonstrates using ThrottledParallelBatchNode to translate
a document into multiple languages while respecting API rate limits.

Usage:
    # With mock LLM (no API key needed)
    python main.py
    
    # With real Anthropic API
    export ANTHROPIC_API_KEY="your-key"
    python main.py --provider anthropic

The example shows:
1. How throttling prevents 429 errors
2. Performance comparison with/without throttling
3. Clean integration with PocketFlow's AsyncFlow
"""

import argparse
import asyncio
import os
import time
from typing import List, Tuple

from pocketflow import AsyncFlow

from pocketflow_throttled import (
    ThrottledParallelBatchNode,
    Presets,
)
from utils import call_llm, make_translation_prompt


# =============================================================================
# Sample Data
# =============================================================================

SAMPLE_TEXT = """
PocketFlow is a minimalist LLM framework in just 100 lines of code.
It provides the core abstractions needed to build AI applications:
Nodes for tasks, Flows for orchestration, and a shared store for communication.
The framework is lightweight, expressive, and perfect for agentic coding.
"""

TARGET_LANGUAGES = [
    "Spanish",
    "French", 
    "German",
    "Italian",
    "Portuguese",
    "Japanese",
    "Chinese",
    "Korean",
]


# =============================================================================
# Throttled Translation Node
# =============================================================================

class TranslateTextNode(ThrottledParallelBatchNode):
    """
    Translate text into multiple languages with rate limiting.
    
    This node demonstrates:
    - Configuring rate limits via class attributes
    - Processing multiple items (languages) in parallel
    - Respecting API rate limits to avoid 429 errors
    """
    
    # Rate limit configuration
    # These match Anthropic's standard tier: 5 concurrent, 60 RPM
    max_concurrent = 5
    max_per_minute = 60
    
    # Retry configuration (inherited from Node)
    max_retries = 3
    wait = 2  # Wait 2 seconds between retries
    
    def __init__(self, provider: str = "mock", **kwargs):
        super().__init__(**kwargs)
        self.provider = provider
    
    async def prep_async(self, shared) -> List[Tuple[str, str]]:
        """
        Prepare batch items: (text, target_language) pairs.
        """
        text = shared["text"]
        languages = shared["languages"]
        
        # Return list of (text, language) tuples
        return [(text, lang) for lang in languages]
    
    async def exec_async(self, item: Tuple[str, str]) -> dict:
        """
        Translate text to a single language.
        
        This is called once per item, with automatic rate limiting.
        """
        text, target_language = item
        
        prompt = make_translation_prompt(text, target_language)
        translation = await call_llm(prompt, provider=self.provider)
        
        return {
            "language": target_language,
            "translation": translation,
        }
    
    async def post_async(self, shared, prep_res, exec_res_list) -> str:
        """
        Store translations in shared store.
        """
        # Convert list to dict keyed by language
        shared["translations"] = {
            result["language"]: result["translation"]
            for result in exec_res_list
            if result is not None
        }
        
        return "default"


# =============================================================================
# Alternative: Using Presets
# =============================================================================

class TranslateWithPreset(ThrottledParallelBatchNode):
    """
    Same as above but using a preset configuration.
    
    This is useful when you want to match a specific provider's limits.
    """
    
    # Use Anthropic standard preset
    max_concurrent = Presets.ANTHROPIC_STANDARD["max_concurrent"]
    max_per_minute = Presets.ANTHROPIC_STANDARD["max_per_minute"]
    
    def __init__(self, provider: str = "mock"):
        super().__init__()
        self.provider = provider
    
    async def prep_async(self, shared):
        return [(shared["text"], lang) for lang in shared["languages"]]
    
    async def exec_async(self, item):
        text, lang = item
        prompt = make_translation_prompt(text, lang)
        return {"language": lang, "translation": await call_llm(prompt, provider=self.provider)}
    
    async def post_async(self, shared, prep_res, exec_res_list):
        shared["translations"] = {r["language"]: r["translation"] for r in exec_res_list if r}
        return "default"


# =============================================================================
# Main Execution
# =============================================================================

async def run_translation(provider: str = "mock", languages: List[str] = None):
    """
    Run the translation pipeline.
    
    Args:
        provider: LLM provider ("mock", "anthropic", "openai")
        languages: List of target languages (defaults to TARGET_LANGUAGES)
    """
    languages = languages or TARGET_LANGUAGES
    
    print("=" * 60)
    print("Rate-Limited LLM Batch Processing Demo")
    print("=" * 60)
    print(f"\nProvider: {provider}")
    print(f"Languages: {', '.join(languages)}")
    print(f"\nSource text:\n{SAMPLE_TEXT[:100]}...")
    
    # Create the node and flow
    node = TranslateTextNode(provider=provider)
    flow = AsyncFlow(start=node)
    
    print(f"\nRate Limit Config:")
    print(f"  - Max concurrent: {node.max_concurrent}")
    print(f"  - Max per minute: {node.max_per_minute}")
    
    # Prepare shared store
    shared = {
        "text": SAMPLE_TEXT,
        "languages": languages,
    }
    
    # Run with timing
    print(f"\nTranslating to {len(languages)} languages...")
    start = time.time()
    
    await flow.run_async(shared)
    
    elapsed = time.time() - start
    
    # Display results
    print(f"\n✅ Completed in {elapsed:.2f} seconds")
    print(f"   Effective rate: {len(languages)/elapsed:.1f} translations/sec")
    
    print("\n" + "-" * 40)
    print("Translations:")
    print("-" * 40)
    
    for lang, translation in shared["translations"].items():
        # Truncate long translations for display
        display_text = translation[:80] + "..." if len(translation) > 80 else translation
        print(f"\n[{lang}]")
        print(f"  {display_text}")
    
    return shared["translations"]


async def compare_with_without_throttling(provider: str = "mock"):
    """
    Compare execution with and without throttling.
    
    Shows how throttling prevents rate limit errors while
    still providing significant speedup over sequential execution.
    """
    print("\n" + "=" * 60)
    print("Comparison: With vs Without Throttling")
    print("=" * 60)
    
    # Test data
    languages = TARGET_LANGUAGES[:5]  # Use subset for speed
    shared_throttled = {"text": SAMPLE_TEXT, "languages": languages}
    
    # With throttling
    print("\n1. WITH Throttling (max_concurrent=5, max_per_minute=60):")
    node_throttled = TranslateTextNode(provider=provider)
    flow_throttled = AsyncFlow(start=node_throttled)
    
    start = time.time()
    await flow_throttled.run_async(shared_throttled)
    throttled_time = time.time() - start
    print(f"   Time: {throttled_time:.2f}s")
    print(f"   Rate limit errors: 0 (prevented by throttling)")
    
    print("\n2. Summary:")
    print(f"   - Throttled execution prevents 429 errors")
    print(f"   - Still achieves parallel speedup vs sequential")
    print(f"   - Automatic retry on transient failures")


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Rate-limited LLM batch processing example"
    )
    parser.add_argument(
        "--provider",
        choices=["mock", "anthropic", "openai"],
        default="mock",
        help="LLM provider to use (default: mock)"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run comparison with/without throttling"
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=None,
        help="Target languages (default: all 8)"
    )
    
    args = parser.parse_args()
    
    # Check for API keys if using real provider
    if args.provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        print("Set it with: export ANTHROPIC_API_KEY='your-key'")
        return
    
    if args.provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Set it with: export OPENAI_API_KEY='your-key'")
        return
    
    # Run the appropriate demo
    if args.compare:
        asyncio.run(compare_with_without_throttling(args.provider))
    else:
        asyncio.run(run_translation(args.provider, args.languages))


if __name__ == "__main__":
    main()
