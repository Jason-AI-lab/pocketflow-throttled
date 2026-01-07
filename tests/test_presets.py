"""
Tests for the Presets module.
"""

import pytest

from pocketflow_throttled import Presets, RateLimitConfig, ThrottledParallelBatchNode


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""
    
    def test_creation(self):
        """Test basic creation of RateLimitConfig."""
        config = RateLimitConfig(
            max_concurrent=5,
            max_per_minute=60,
            description="Test config"
        )
        
        assert config.max_concurrent == 5
        assert config.max_per_minute == 60
        assert config.description == "Test config"
    
    def test_immutability(self):
        """Test that RateLimitConfig is immutable (frozen)."""
        config = RateLimitConfig(max_concurrent=5, max_per_minute=60)
        
        with pytest.raises(AttributeError):
            config.max_concurrent = 10
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = RateLimitConfig(max_concurrent=5, max_per_minute=60)
        d = config.to_dict()
        
        assert d == {"max_concurrent": 5, "max_per_minute": 60}
    
    def test_to_dict_none_max_per_minute(self):
        """Test that None max_per_minute is excluded from dict."""
        config = RateLimitConfig(max_concurrent=10, max_per_minute=None)
        d = config.to_dict()
        
        assert d == {"max_concurrent": 10}
        assert "max_per_minute" not in d


class TestPresetsDict:
    """Tests for preset dictionary values."""
    
    def test_openai_presets_exist(self):
        """Test that OpenAI presets are defined."""
        assert hasattr(Presets, "OPENAI_FREE")
        assert hasattr(Presets, "OPENAI_TIER1")
        assert hasattr(Presets, "OPENAI_TIER2")
        assert hasattr(Presets, "OPENAI_TIER3")
        assert hasattr(Presets, "OPENAI_TIER4")
        assert hasattr(Presets, "OPENAI_TIER5")
    
    def test_anthropic_presets_exist(self):
        """Test that Anthropic presets are defined."""
        assert hasattr(Presets, "ANTHROPIC_FREE")
        assert hasattr(Presets, "ANTHROPIC_BUILD_TIER1")
        assert hasattr(Presets, "ANTHROPIC_STANDARD")
        assert hasattr(Presets, "ANTHROPIC_SCALE")
    
    def test_generic_presets_exist(self):
        """Test that generic presets are defined."""
        assert hasattr(Presets, "CONSERVATIVE")
        assert hasattr(Presets, "MODERATE")
        assert hasattr(Presets, "AGGRESSIVE")
    
    def test_preset_structure(self):
        """Test that presets have correct structure."""
        preset = Presets.OPENAI_TIER1
        
        assert "max_concurrent" in preset
        assert "max_per_minute" in preset
        assert isinstance(preset["max_concurrent"], int)
        assert isinstance(preset["max_per_minute"], int)
    
    def test_preset_values_reasonable(self):
        """Test that preset values are reasonable."""
        # Conservative should be lower than aggressive
        assert Presets.CONSERVATIVE["max_concurrent"] < Presets.AGGRESSIVE["max_concurrent"]
        assert Presets.CONSERVATIVE["max_per_minute"] < Presets.AGGRESSIVE["max_per_minute"]
        
        # OpenAI tiers should increase
        assert Presets.OPENAI_TIER1["max_per_minute"] < Presets.OPENAI_TIER2["max_per_minute"]
        assert Presets.OPENAI_TIER2["max_per_minute"] < Presets.OPENAI_TIER3["max_per_minute"]


class TestPresetsGet:
    """Tests for Presets.get() method."""
    
    def test_get_by_name_lowercase(self):
        """Test getting preset by lowercase name."""
        preset = Presets.get("openai_tier1")
        
        assert preset["max_concurrent"] == Presets.OPENAI_TIER1["max_concurrent"]
        assert preset["max_per_minute"] == Presets.OPENAI_TIER1["max_per_minute"]
    
    def test_get_by_name_uppercase(self):
        """Test getting preset by uppercase name."""
        preset = Presets.get("OPENAI_TIER1")
        
        assert preset == Presets.OPENAI_TIER1
    
    def test_get_unknown_preset_raises(self):
        """Test that getting unknown preset raises KeyError."""
        with pytest.raises(KeyError, match="Unknown preset"):
            Presets.get("nonexistent_preset")
    
    def test_get_returns_usable_dict(self):
        """Test that get() returns dict usable with **kwargs."""
        preset = Presets.get("moderate")
        
        # Should be able to unpack into node
        node = ThrottledParallelBatchNode(**preset)
        
        assert node.max_concurrent == Presets.MODERATE["max_concurrent"]
        assert node.max_per_minute == Presets.MODERATE["max_per_minute"]


class TestPresetsConfigs:
    """Tests for Presets.CONFIGS typed configurations."""
    
    def test_configs_dict_exists(self):
        """Test that CONFIGS dict is populated."""
        assert len(Presets.CONFIGS) > 0
    
    def test_configs_are_rate_limit_config(self):
        """Test that all CONFIGS values are RateLimitConfig instances."""
        for name, config in Presets.CONFIGS.items():
            assert isinstance(config, RateLimitConfig), f"{name} is not RateLimitConfig"
    
    def test_configs_have_descriptions(self):
        """Test that configs have descriptions."""
        for name, config in Presets.CONFIGS.items():
            # Description can be empty string but should exist
            assert hasattr(config, "description")


class TestPresetsListPresets:
    """Tests for Presets.list_presets() method."""
    
    def test_list_presets_returns_dict(self):
        """Test that list_presets returns a dictionary."""
        presets = Presets.list_presets()
        
        assert isinstance(presets, dict)
        assert len(presets) > 0
    
    def test_list_presets_values_are_strings(self):
        """Test that list_presets values are description strings."""
        presets = Presets.list_presets()
        
        for name, description in presets.items():
            assert isinstance(name, str)
            assert isinstance(description, str)


class TestPresetsWithNode:
    """Integration tests using presets with ThrottledParallelBatchNode."""
    
    def test_openai_tier1_with_node(self):
        """Test using OpenAI Tier 1 preset with node."""
        node = ThrottledParallelBatchNode(**Presets.OPENAI_TIER1)
        
        assert node.max_concurrent == 5
        assert node.max_per_minute == 60
    
    def test_conservative_with_node(self):
        """Test using conservative preset with node."""
        node = ThrottledParallelBatchNode(**Presets.CONSERVATIVE)
        
        assert node.max_concurrent == 2
        assert node.max_per_minute == 20
    
    def test_class_attribute_override_with_preset(self):
        """Test using preset as class attributes."""
        class MyNode(ThrottledParallelBatchNode):
            max_concurrent = Presets.ANTHROPIC_STANDARD["max_concurrent"]
            max_per_minute = Presets.ANTHROPIC_STANDARD["max_per_minute"]
        
        node = MyNode()
        
        assert node.max_concurrent == Presets.ANTHROPIC_STANDARD["max_concurrent"]
        assert node.max_per_minute == Presets.ANTHROPIC_STANDARD["max_per_minute"]
    
    def test_get_with_node(self):
        """Test using Presets.get() with node."""
        config = Presets.get("google_free")
        node = ThrottledParallelBatchNode(**config)
        
        assert node.max_concurrent == Presets.GOOGLE_FREE["max_concurrent"]
        assert node.max_per_minute == Presets.GOOGLE_FREE["max_per_minute"]


class TestScrapingPresets:
    """Tests for web scraping presets."""
    
    def test_scraping_presets_exist(self):
        """Test that scraping presets are defined."""
        assert hasattr(Presets, "SCRAPING_POLITE")
        assert hasattr(Presets, "SCRAPING_MODERATE")
        assert hasattr(Presets, "SCRAPING_AGGRESSIVE")
    
    def test_scraping_presets_are_polite(self):
        """Test that scraping presets have reasonable limits."""
        # Polite should be very conservative
        assert Presets.SCRAPING_POLITE["max_concurrent"] <= 3
        assert Presets.SCRAPING_POLITE["max_per_minute"] <= 20
