"""
Utility functions for LLM API calls.

This module provides async wrappers for various LLM providers.
Replace with your preferred provider or use the mock for testing.
"""

import asyncio
import os
import random
from typing import Optional

# Try to import LLM client libraries
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# =============================================================================
# Mock LLM for Testing (no API key needed)
# =============================================================================

async def call_llm_mock(prompt: str, delay: float = 0.1) -> str:
    """
    Mock LLM call for testing without API keys.
    
    Simulates API latency and occasionally fails with rate limit errors
    to demonstrate throttling behavior.
    
    Args:
        prompt: The prompt to "process"
        delay: Simulated API latency in seconds
        
    Returns:
        A mock response string
    """
    # Simulate network latency
    await asyncio.sleep(delay + random.uniform(0, 0.05))
    
    # Occasionally simulate rate limit (5% chance)
    if random.random() < 0.05:
        raise Exception("429 Too Many Requests - Rate limit exceeded")
    
    # Return mock response
    return f"[Mock Response] Processed: {prompt[:50]}..."


# =============================================================================
# Anthropic Claude API
# =============================================================================

async def call_anthropic(
    prompt: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1024,
    api_key: Optional[str] = None,
) -> str:
    """
    Call Anthropic Claude API asynchronously.
    
    Args:
        prompt: The prompt to send to Claude
        model: Model to use (default: claude-sonnet-4-20250514)
        max_tokens: Maximum tokens in response
        api_key: API key (defaults to ANTHROPIC_API_KEY env var)
        
    Returns:
        The model's response text
        
    Raises:
        ImportError: If anthropic package is not installed
        anthropic.RateLimitError: If rate limit is exceeded
    """
    if not ANTHROPIC_AVAILABLE:
        raise ImportError(
            "anthropic package not installed. "
            "Install with: pip install anthropic"
        )
    
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    
    client = anthropic.AsyncAnthropic(api_key=api_key)
    
    message = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return message.content[0].text


# =============================================================================
# OpenAI API
# =============================================================================

async def call_openai(
    prompt: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 1024,
    api_key: Optional[str] = None,
) -> str:
    """
    Call OpenAI API asynchronously.
    
    Args:
        prompt: The prompt to send
        model: Model to use (default: gpt-4o-mini)
        max_tokens: Maximum tokens in response
        api_key: API key (defaults to OPENAI_API_KEY env var)
        
    Returns:
        The model's response text
        
    Raises:
        ImportError: If openai package is not installed
        openai.RateLimitError: If rate limit is exceeded
    """
    if not OPENAI_AVAILABLE:
        raise ImportError(
            "openai package not installed. "
            "Install with: pip install openai"
        )
    
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    
    client = openai.AsyncOpenAI(api_key=api_key)
    
    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response.choices[0].message.content


# =============================================================================
# Generic LLM Interface
# =============================================================================

async def call_llm(
    prompt: str,
    provider: str = "mock",
    **kwargs
) -> str:
    """
    Call an LLM provider.
    
    This is a unified interface that routes to the appropriate provider.
    
    Args:
        prompt: The prompt to send
        provider: Which provider to use ("mock", "anthropic", "openai")
        **kwargs: Provider-specific arguments
        
    Returns:
        The model's response text
        
    Example:
        ```python
        # Use mock for testing
        response = await call_llm("Hello!", provider="mock")
        
        # Use Anthropic
        response = await call_llm("Hello!", provider="anthropic")
        
        # Use OpenAI with specific model
        response = await call_llm("Hello!", provider="openai", model="gpt-4")
        ```
    """
    providers = {
        "mock": call_llm_mock,
        "anthropic": call_anthropic,
        "openai": call_openai,
    }
    
    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(providers.keys())}")
    
    return await providers[provider](prompt, **kwargs)


# =============================================================================
# Translation Prompt Helper
# =============================================================================

def make_translation_prompt(text: str, target_language: str) -> str:
    """
    Create a translation prompt.
    
    Args:
        text: Text to translate
        target_language: Target language name (e.g., "Spanish", "French")
        
    Returns:
        Formatted translation prompt
    """
    return f"""Translate the following text to {target_language}. 
Only respond with the translation, no explanations.

Text to translate:
{text}"""


# =============================================================================
# Main - Test the utilities
# =============================================================================

if __name__ == "__main__":
    async def test():
        print("Testing LLM utilities...")
        
        # Test mock
        print("\n1. Testing mock LLM:")
        response = await call_llm("What is 2+2?", provider="mock")
        print(f"   Response: {response}")
        
        # Test translation prompt
        print("\n2. Testing translation prompt:")
        prompt = make_translation_prompt("Hello, world!", "Spanish")
        print(f"   Prompt: {prompt[:100]}...")
        
        # Test real API if available
        if os.getenv("ANTHROPIC_API_KEY"):
            print("\n3. Testing Anthropic API:")
            try:
                response = await call_llm("Say hello in French", provider="anthropic")
                print(f"   Response: {response}")
            except Exception as e:
                print(f"   Error: {e}")
        else:
            print("\n3. Skipping Anthropic API test (no API key)")
        
        print("\nDone!")
    
    asyncio.run(test())
