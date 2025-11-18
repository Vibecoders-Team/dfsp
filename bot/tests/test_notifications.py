"""Integration tests for notification consumer."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from redis import asyncio as aioredis

# Добавляем корень проекта (bot/) в sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.notifications.consumer import NotificationConsumer


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis_mock = AsyncMock(spec=aioredis.Redis)
    redis_mock.blpop = AsyncMock(return_value=None)  # No events by default
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()
    redis_mock.exists = AsyncMock(return_value=False)
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock()
    redis_mock.lrange = AsyncMock(return_value=[])
    redis_mock.delete = AsyncMock()
    redis_mock.rpush = AsyncMock()
    redis_mock.sadd = AsyncMock(return_value=1)  # New event
    redis_mock.set = AsyncMock(return_value=True)  # For deduplication
    return redis_mock


@pytest.fixture
def mock_bot():
    """Mock Telegram bot."""
    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def sample_grant_created_event():
    """Sample grant_created event."""
    return {
        "event_id": "test-grant-created-1",
        "version": 1,
        "type": "grant_created",
        "source": "api",
        "ts": datetime.now(UTC).isoformat(),
        "subject": {
            "capId": "0x" + "ab" * 32,
            "fileId": "0x" + "cd" * 32,
            "grantor": "0x1234567890123456789012345678901234567890",
            "grantee": "0x0987654321098765432109876543210987654321",
        },
        "data": {
            "ttlDays": 30,
            "maxDownloads": 10,
        },
    }


@pytest.fixture
def sample_download_denied_event():
    """Sample download_denied event."""
    return {
        "event_id": "test-download-denied-1",
        "version": 1,
        "type": "download_denied",
        "source": "api",
        "ts": datetime.now(UTC).isoformat(),
        "subject": {
            "capId": "0x" + "ef" * 32,
            "fileId": "0x" + "12" * 32,
            "user": "0x0987654321098765432109876543210987654321",
        },
        "data": {
            "reason": "not_grantee",
            "statusCode": 403,
        },
    }


@pytest.mark.asyncio
async def test_consumer_processes_grant_created(mock_redis, mock_bot, sample_grant_created_event):
    """Test consumer processes grant_created event."""
    # Setup: event in queue, chat_id resolved from event
    event_json = json.dumps(sample_grant_created_event).encode()
    mock_redis.blpop = AsyncMock(return_value=("events:queue", event_json))
    # Address resolver will try to get chat_id from cache, then resolve from event
    mock_redis.get = AsyncMock(return_value=None)  # Not in cache
    mock_redis.exists = AsyncMock(return_value=False)  # Not duplicate
    mock_redis.sadd = AsyncMock(return_value=1)  # Mark as seen
    mock_redis.setex = AsyncMock()  # Cache chat_id

    consumer = NotificationConsumer(mock_bot, mock_redis)
    consumer.running = True

    # Mock address resolver to return chat_id directly
    async def mock_resolve(event):
        return 123456789

    consumer.address_resolver.resolve_from_event = mock_resolve

    # Process one event
    await consumer._consume_batch()

    # Verify: should send message to chat_id
    mock_bot.send_message.assert_called_once()
    call_args = mock_bot.send_message.call_args
    assert call_args.kwargs["chat_id"] == 123456789
    assert "Grant создан" in call_args.kwargs["text"] or "grant" in call_args.kwargs["text"].lower()


@pytest.mark.asyncio
async def test_consumer_skips_duplicate(mock_redis, mock_bot, sample_grant_created_event):
    """Test consumer skips duplicate events."""
    event_json = json.dumps(sample_grant_created_event).encode()
    mock_redis.blpop = AsyncMock(return_value=("events:queue", event_json))
    mock_redis.exists = AsyncMock(return_value=True)  # Duplicate
    mock_redis.sadd = AsyncMock(return_value=0)  # Already seen

    consumer = NotificationConsumer(mock_bot, mock_redis)
    consumer.running = True

    await consumer._consume_batch()

    # Should not send message
    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_skips_unknown_event_type(mock_redis, mock_bot):
    """Test consumer skips unknown event types."""
    unknown_event = {
        "event_id": "test-unknown-1",
        "version": 1,
        "type": "unknown_event_type",
        "source": "api",
        "ts": datetime.now(UTC).isoformat(),
        "subject": {},
        "data": {},
    }
    event_json = json.dumps(unknown_event).encode()
    mock_redis.blpop = AsyncMock(return_value=("events:queue", event_json))

    consumer = NotificationConsumer(mock_bot, mock_redis)
    consumer.running = True

    await consumer._consume_batch()

    # Should not send message
    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_handles_missing_chat_id(mock_redis, mock_bot, sample_grant_created_event):
    """Test consumer handles missing chat_id gracefully."""
    event_json = json.dumps(sample_grant_created_event).encode()
    mock_redis.blpop = AsyncMock(return_value=("events:queue", event_json))
    mock_redis.get = AsyncMock(return_value=None)  # No chat_id cached
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.sadd = AsyncMock(return_value=1)

    consumer = NotificationConsumer(mock_bot, mock_redis)
    consumer.running = True

    await consumer._consume_batch()

    # Should not send message (no chat_id)
    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_handles_daily_limit(mock_redis, mock_bot, sample_grant_created_event):
    """Test consumer respects daily limits."""
    event_json = json.dumps(sample_grant_created_event).encode()
    mock_redis.blpop = AsyncMock(return_value=("events:queue", event_json))
    mock_redis.get = AsyncMock(return_value=b"123456789")
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.sadd = AsyncMock(return_value=1)
    # Daily limit exceeded (hard limit)
    mock_redis.incr = AsyncMock(return_value=101)  # > 100

    consumer = NotificationConsumer(mock_bot, mock_redis)
    consumer.running = True

    await consumer._consume_batch()

    # Should not send message (dropped due to limit)
    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_handles_retry_after(mock_redis, mock_bot, sample_grant_created_event):
    """Test consumer handles Telegram rate limits."""
    from aiogram.exceptions import TelegramRetryAfter

    event_json = json.dumps(sample_grant_created_event).encode()
    mock_redis.blpop = AsyncMock(return_value=("events:queue", event_json))
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.sadd = AsyncMock(return_value=1)
    mock_redis.setex = AsyncMock()

    # First call raises rate limit, second succeeds
    mock_bot.send_message = AsyncMock(
        side_effect=[
            TelegramRetryAfter(method="sendMessage", message="Rate limit", retry_after=1),
            None,  # Success
        ]
    )

    consumer = NotificationConsumer(mock_bot, mock_redis)
    consumer.running = True

    # Mock address resolver to return chat_id directly
    async def mock_resolve(event):
        return 123456789

    consumer.address_resolver.resolve_from_event = mock_resolve

    await consumer._consume_batch()

    # Should retry and eventually send
    assert mock_bot.send_message.call_count == 2


@pytest.mark.asyncio
async def test_consumer_processes_download_denied(mock_redis, mock_bot, sample_download_denied_event):
    """Test consumer processes download_denied event."""
    event_json = json.dumps(sample_download_denied_event).encode()
    mock_redis.blpop = AsyncMock(return_value=("events:queue", event_json))
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.sadd = AsyncMock(return_value=1)
    mock_redis.setex = AsyncMock()

    consumer = NotificationConsumer(mock_bot, mock_redis)
    consumer.running = True

    # Mock address resolver to return chat_id directly
    async def mock_resolve(event):
        return 987654321

    consumer.address_resolver.resolve_from_event = mock_resolve

    await consumer._consume_batch()

    # Verify: should send message
    mock_bot.send_message.assert_called_once()
    call_args = mock_bot.send_message.call_args
    assert call_args.kwargs["chat_id"] == 987654321
    assert "отклонено" in call_args.kwargs["text"].lower() or "denied" in call_args.kwargs["text"].lower()
