"""
Rate Limit Presets
==================

Pre-configured rate limit settings for popular LLM and API services.

These presets are based on documented rate limits and common usage patterns.
Always verify current limits with your specific API tier and provider.

Usage:
    ```python
    from pocketflow_throttled import ThrottledParallelBatchNode, Presets
    
    class MyNode(ThrottledParallelBatchNode):
        # Use OpenAI Tier 1 limits
        max_concurrent = Presets.OPENAI_TIER1["max_concurrent"]
        max_per_minute = Presets.OPENAI_TIER1["max_per_minute"]
    
    # Or pass as kwargs
    node = ThrottledParallelBatchNode(**Presets.ANTHROPIC_STANDARD)
    ```
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class RateLimitConfig:
    """
    Immutable rate limit configuration.
    
    Attributes:
        max_concurrent: Maximum simultaneous requests
        max_per_minute: Maximum requests per minute (None = unlimited)
        description: Human-readable description of this preset
    """
    max_concurrent: int
    max_per_minute: Optional[int]
    description: str = ""
    
    def to_dict(self) -> Dict[str, int]:
        """Convert to kwargs dict for node initialization."""
        result = {"max_concurrent": self.max_concurrent}
        if self.max_per_minute is not None:
            result["max_per_minute"] = self.max_per_minute
        return result


class Presets:
    """
    Collection of rate limit presets for popular services.
    
    Each preset is available as both a dict (for **kwargs) and
    a RateLimitConfig object (for programmatic access).
    
    Example:
        ```python
        # Using dict unpacking
        node = ThrottledParallelBatchNode(**Presets.OPENAI_TIER1)
        
        # Using config object
        config = Presets.CONFIGS["openai_tier1"]
        print(f"Limit: {config.max_per_minute} RPM")
        node = ThrottledParallelBatchNode(**config.to_dict())
        ```
    
    Note:
        Rate limits vary by account tier, model, and time. These presets
        represent typical starting points - adjust based on your actual limits.
    """
    
    # =========================================================================
    # OpenAI API Rate Limits (as of 2024)
    # https://platform.openai.com/docs/guides/rate-limits
    # =========================================================================
    
    OPENAI_FREE = {
        "max_concurrent": 3,
        "max_per_minute": 3,
    }
    
    OPENAI_TIER1 = {
        "max_concurrent": 5,
        "max_per_minute": 60,
    }
    
    OPENAI_TIER2 = {
        "max_concurrent": 10,
        "max_per_minute": 500,
    }
    
    OPENAI_TIER3 = {
        "max_concurrent": 15,
        "max_per_minute": 5000,
    }
    
    OPENAI_TIER4 = {
        "max_concurrent": 20,
        "max_per_minute": 10000,
    }
    
    OPENAI_TIER5 = {
        "max_concurrent": 30,
        "max_per_minute": 30000,
    }
    
    # =========================================================================
    # Anthropic Claude API Rate Limits
    # https://docs.anthropic.com/claude/reference/rate-limits
    # =========================================================================
    
    ANTHROPIC_FREE = {
        "max_concurrent": 2,
        "max_per_minute": 5,
    }
    
    ANTHROPIC_BUILD_TIER1 = {
        "max_concurrent": 5,
        "max_per_minute": 50,
    }
    
    ANTHROPIC_BUILD_TIER2 = {
        "max_concurrent": 10,
        "max_per_minute": 1000,
    }
    
    ANTHROPIC_BUILD_TIER3 = {
        "max_concurrent": 15,
        "max_per_minute": 2000,
    }
    
    ANTHROPIC_BUILD_TIER4 = {
        "max_concurrent": 20,
        "max_per_minute": 4000,
    }
    
    # Convenience aliases
    ANTHROPIC_STANDARD = ANTHROPIC_BUILD_TIER1
    ANTHROPIC_SCALE = ANTHROPIC_BUILD_TIER3
    
    # =========================================================================
    # Google AI (Gemini) Rate Limits
    # https://ai.google.dev/pricing
    # =========================================================================
    
    GOOGLE_FREE = {
        "max_concurrent": 2,
        "max_per_minute": 15,
    }
    
    GOOGLE_PAY_AS_YOU_GO = {
        "max_concurrent": 10,
        "max_per_minute": 1000,
    }
    
    # =========================================================================
    # Cohere API Rate Limits
    # https://docs.cohere.com/docs/rate-limits
    # =========================================================================
    
    COHERE_TRIAL = {
        "max_concurrent": 2,
        "max_per_minute": 20,
    }
    
    COHERE_PRODUCTION = {
        "max_concurrent": 10,
        "max_per_minute": 10000,
    }
    
    # =========================================================================
    # Hugging Face Inference API
    # =========================================================================
    
    HUGGINGFACE_FREE = {
        "max_concurrent": 1,
        "max_per_minute": 30,
    }
    
    HUGGINGFACE_PRO = {
        "max_concurrent": 5,
        "max_per_minute": 1000,
    }
    
    # =========================================================================
    # Mistral AI Rate Limits
    # =========================================================================
    
    MISTRAL_FREE = {
        "max_concurrent": 2,
        "max_per_minute": 30,
    }
    
    MISTRAL_STANDARD = {
        "max_concurrent": 10,
        "max_per_minute": 500,
    }
    
    # =========================================================================
    # Generic / Conservative Presets
    # Use these when you don't know the exact limits
    # =========================================================================
    
    CONSERVATIVE = {
        "max_concurrent": 2,
        "max_per_minute": 20,
    }
    
    MODERATE = {
        "max_concurrent": 5,
        "max_per_minute": 60,
    }
    
    AGGRESSIVE = {
        "max_concurrent": 10,
        "max_per_minute": 200,
    }
    
    UNLIMITED_CONCURRENT = {
        "max_concurrent": 50,
        "max_per_minute": None,
    }
    
    # =========================================================================
    # Web Scraping Presets (be respectful to servers)
    # =========================================================================
    
    SCRAPING_POLITE = {
        "max_concurrent": 2,
        "max_per_minute": 10,
    }
    
    SCRAPING_MODERATE = {
        "max_concurrent": 5,
        "max_per_minute": 30,
    }
    
    SCRAPING_AGGRESSIVE = {
        "max_concurrent": 10,
        "max_per_minute": 60,
    }
    
    # =========================================================================
    # Typed Configuration Objects
    # =========================================================================
    
    CONFIGS: Dict[str, RateLimitConfig] = {
        # OpenAI
        "openai_free": RateLimitConfig(3, 3, "OpenAI Free Tier"),
        "openai_tier1": RateLimitConfig(5, 60, "OpenAI Tier 1"),
        "openai_tier2": RateLimitConfig(10, 500, "OpenAI Tier 2"),
        "openai_tier3": RateLimitConfig(15, 5000, "OpenAI Tier 3"),
        "openai_tier4": RateLimitConfig(20, 10000, "OpenAI Tier 4"),
        "openai_tier5": RateLimitConfig(30, 30000, "OpenAI Tier 5"),
        
        # Anthropic
        "anthropic_free": RateLimitConfig(2, 5, "Anthropic Free Tier"),
        "anthropic_tier1": RateLimitConfig(5, 50, "Anthropic Build Tier 1"),
        "anthropic_tier2": RateLimitConfig(10, 1000, "Anthropic Build Tier 2"),
        "anthropic_tier3": RateLimitConfig(15, 2000, "Anthropic Build Tier 3"),
        "anthropic_tier4": RateLimitConfig(20, 4000, "Anthropic Build Tier 4"),
        
        # Google
        "google_free": RateLimitConfig(2, 15, "Google AI Free"),
        "google_paid": RateLimitConfig(10, 1000, "Google AI Pay-as-you-go"),
        
        # Generic
        "conservative": RateLimitConfig(2, 20, "Conservative - safe default"),
        "moderate": RateLimitConfig(5, 60, "Moderate - balanced"),
        "aggressive": RateLimitConfig(10, 200, "Aggressive - high throughput"),
    }
    
    @classmethod
    def get(cls, name: str) -> Dict[str, int]:
        """
        Get a preset by name (case-insensitive).
        
        Args:
            name: Preset name (e.g., "openai_tier1", "ANTHROPIC_STANDARD")
            
        Returns:
            Dict with max_concurrent and max_per_minute keys
            
        Raises:
            KeyError: If preset name is not found
        """
        # Try as attribute first
        name_upper = name.upper()
        if hasattr(cls, name_upper):
            return getattr(cls, name_upper)
        
        # Try in CONFIGS dict
        name_lower = name.lower()
        if name_lower in cls.CONFIGS:
            return cls.CONFIGS[name_lower].to_dict()
        
        raise KeyError(
            f"Unknown preset: {name}. "
            f"Available: {list(cls.CONFIGS.keys())}"
        )
    
    @classmethod
    def list_presets(cls) -> Dict[str, str]:
        """
        List all available presets with descriptions.
        
        Returns:
            Dict mapping preset names to descriptions
        """
        return {name: config.description for name, config in cls.CONFIGS.items()}
