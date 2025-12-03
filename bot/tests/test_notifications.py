"""Integration-ish tests for notification consumer (coalescing, dedup, limits)."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from redis import asyncio as aioredis

from app.services.notifications.consumer import NotificationConsumer, QueueMessage


@pytest.fixture(autouse=True)
def patch_get_message(monkeypatch):
    async def _fake_get_message(key: str, *, language: str | None = None, variables: dict | None = None) -> str:
        return f"{key}:{variables}" if variables else key

    monkeypatch.setattr("app.services.notifications.formatter.get_message", _fake_get_message)
    return _fake_get_message


def _build_message(event_id: str, chat_id: int = 123, event_type: str = "grant_created") -> QueueMessage:
    fields = {
        "id": event_id,
        "type": event_type,
        "chat_id": chat_id,
        "ts": datetime.now(UTC).isoformat(),
        "payload": {"capId": "0x" + "ab" * 32, "fileId": "0x" + "cd" * 32},
    }
    ack = AsyncMock()
    return QueueMessage(event_id, fields, ack=ack)


@pytest.fixture
def mock_redis():
    redis_mock = AsyncMock(spec=aioredis.Redis)
    redis_mock.sadd = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock()
    redis_mock.incrby = AsyncMock(return_value=1)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock()
    redis_mock.delete = AsyncMock()
    return redis_mock


@pytest.fixture
def mock_bot():
    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock()
    return bot


@pytest.mark.asyncio
async def test_coalesce_window_sends_single_message(mock_redis, mock_bot):
    consumer = NotificationConsumer(mock_bot, mock_redis)
    consumer.antispam.coalesce_window = 0.01

    messages = [_build_message(f"evt-{i}") for i in range(3)]
    for msg in messages:
        await consumer._handle_message(msg)
    await asyncio.sleep(0.05)

    assert mock_bot.send_message.call_count == 1
    for msg in messages:
        msg.ack.assert_awaited()


@pytest.mark.asyncio
async def test_unsubscribed_chat_drops_events(mock_redis, mock_bot):
    mock_redis.get = AsyncMock(return_value=b"0")  # subscription flag
    consumer = NotificationConsumer(mock_bot, mock_redis)
    msg = _build_message("evt-sub-off")

    await consumer._handle_message(msg)

    mock_bot.send_message.assert_not_called()
    msg.ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_daily_limit_blocks_delivery(mock_redis, mock_bot):
    mock_redis.incrby = AsyncMock(return_value=9999)  # exceed limit immediately
    consumer = NotificationConsumer(mock_bot, mock_redis)
    consumer.antispam.coalesce_window = 0.0
    msg = _build_message("evt-limit")

    await consumer._handle_message(msg)
    await asyncio.sleep(0.01)

    mock_bot.send_message.assert_not_called()
    msg.ack.assert_awaited_once()
