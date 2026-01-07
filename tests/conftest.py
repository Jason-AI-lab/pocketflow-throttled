"""
Pytest configuration and fixtures for pocketflow_throttled tests.
"""

import asyncio
import pytest


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def shared_store():
    """Create a fresh shared store for each test."""
    return {}


@pytest.fixture
def sample_items():
    """Sample items for batch processing tests."""
    return list(range(10))


@pytest.fixture
def large_batch():
    """Larger batch for stress testing."""
    return list(range(100))
