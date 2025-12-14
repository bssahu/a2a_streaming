"""
Pytest configuration and fixtures for A2A Customer Service tests.
"""

import os
import sys
from typing import AsyncGenerator

import pytest
import pytest_asyncio
import redis.exceptions

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.redis_manager import RedisManager
from common.a2a_protocol import Message, TextPart


@pytest_asyncio.fixture
async def redis_manager() -> AsyncGenerator[RedisManager, None]:
    """Create a Redis manager connected to test Redis."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    manager = RedisManager(url=redis_url, db=15)  # Use db 15 for tests
    
    try:
        await manager.connect()
    except redis.exceptions.ConnectionError:
        # If Redis isn't running locally, fall back to an in-memory fake so tests
        # are hermetic and don't require external services.
        try:
            import fakeredis.aioredis as fakeredis_aioredis
        except ImportError:  # pragma: no cover
            pytest.skip("Redis not available and fakeredis not installed")
        manager._client = fakeredis_aioredis.FakeRedis(decode_responses=True, db=15)
        yield manager
    finally:
        # Cleanup test data
        if manager._client:
            await manager._client.flushdb()
        # RedisManager.disconnect() assumes an awaitable close() method; fakeredis
        # provides that, but guard just in case.
        try:
            await manager.disconnect()
        except TypeError:
            pass


@pytest.fixture
def sample_message() -> Message:
    """Create a sample user message."""
    return Message(
        role="user",
        parts=[TextPart(text="I would like to book an appointment for tomorrow at 2pm")],
    )


@pytest.fixture
def booking_message() -> Message:
    """Create a booking-related message."""
    return Message(
        role="user",
        parts=[TextPart(text="Book a table for 2 on Friday at 7pm")],
    )


@pytest.fixture
def billing_message() -> Message:
    """Create a billing-related message."""
    return Message(
        role="user",
        parts=[TextPart(text="Show me my pending invoices")],
    )


@pytest.fixture
def general_message() -> Message:
    """Create a general inquiry message."""
    return Message(
        role="user",
        parts=[TextPart(text="What services do you offer?")],
    )



