"""Notification consumer for tg.notifications.* queue."""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from redis import asyncio as aioredis
from redis.exceptions import ResponseError

from ...config import settings
from ...metrics import tg_notify_dropped_total, tg_notify_sent_total
from ...services.dfsp_api import prepare_download
from .antispam import AntiSpam
from .formatter import format_coalesced, format_notification
from .models import CoalescedNotification, NotificationEvent
from .preferences import NotificationPreferences
from .retry import RetryConfig, send_with_retry

logger = logging.getLogger(__name__)

NOTIFICATION_EVENT_TYPES = {
    "grant_created",
    "grant_received",
    "grant_revoked",
    "download_allowed",
    "download_denied",
    "anchor_ok",
    "relayer_warn",
}


class QueueMessage:
    """Wrapper for queue message with ack callback."""

    def __init__(self, raw_id: str, fields: Mapping[str, Any], ack: Callable[[], Awaitable[None]]) -> None:
        self.raw_id = raw_id
        self.fields = fields
        self.ack = ack


class RedisStreamQueue:
    """Adapter for Redis Streams."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        stream_key: str,
        group: str,
        consumer_name: str,
    ) -> None:
        self.redis = redis_client
        self.stream_key = stream_key
        self.group = group
        self.consumer_name = consumer_name

    async def init(self) -> None:
        try:
            await self.redis.xgroup_create(self.stream_key, self.group, id="$", mkstream=True)
            logger.info("Created Redis consumer group %s for %s", self.group, self.stream_key)
        except ResponseError as exc:
            # BUSYGROUP means it already exists — fine
            if "BUSYGROUP" not in str(exc):
                raise

    async def read_batch(self, count: int = 20, block_ms: int = 1000) -> list[QueueMessage]:
        try:
            res = await self.redis.xreadgroup(
                groupname=self.group,
                consumername=self.consumer_name,
                streams={self.stream_key: ">"},
                count=count,
                block=block_ms,
            )
        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                await self.init()
                res = await self.redis.xreadgroup(
                    groupname=self.group,
                    consumername=self.consumer_name,
                    streams={self.stream_key: ">"},
                    count=count,
                    block=block_ms,
                )
            else:
                raise
        messages: list[QueueMessage] = []
        for _stream, entries in res:
            for message_id, fields in entries:
                ack_fn = functools.partial(self.redis.xack, self.stream_key, self.group, message_id)
                messages.append(QueueMessage(str(message_id), fields, ack=ack_fn))
        return messages

    async def close(self) -> None:  # pragma: no cover - nothing to close for aioredis
        return None


class RabbitQueue:
    """Adapter for RabbitMQ (AMQP). Minimal implementation to satisfy env-driven queue choice."""

    def __init__(self, dsn: str, queue_name: str) -> None:
        self.dsn = dsn
        self.queue_name = queue_name
        self.connection: Any = None
        self.channel: Any = None
        self.queue: Any = None

    async def init(self) -> None:
        import aio_pika  # type: ignore

        self.connection = await aio_pika.connect_robust(self.dsn)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=50)
        self.queue = await self.channel.declare_queue(self.queue_name, durable=True)
        logger.info("Connected to RabbitMQ queue %s", self.queue_name)

    async def read_batch(self, count: int = 20, block_ms: int = 1000) -> list[QueueMessage]:
        import aio_pika  # type: ignore

        messages: list[QueueMessage] = []
        timeout = block_ms / 1000
        for _ in range(count):
            try:
                try:
                    msg = await self.queue.get(timeout=timeout, fail=False)  # type: ignore[call-arg]
                except TypeError:
                    msg = await self.queue.get(timeout=timeout)
            except aio_pika.exceptions.QueueEmpty:  # type: ignore[attr-defined]
                break
            if msg is None:
                break
            try:
                payload = json.loads(msg.body.decode()) if msg.body else {}
            except json.JSONDecodeError:
                payload = {}
            raw_id = payload.get("id") or msg.message_id or str(uuid.uuid4())
            messages.append(QueueMessage(raw_id, payload, ack=msg.ack))  # type: ignore[arg-type]
        return messages

    async def close(self) -> None:
        try:
            if self.connection:
                await self.connection.close()
        except Exception as exc:
            logger.debug("RabbitMQ close failed: %s", exc)


class NotificationConsumer:
    """Consumer for notification events."""

    def __init__(
        self,
        bot: Bot,
        redis_client: aioredis.Redis,
        queue_dsn: str | None = None,
    ) -> None:
        self.bot = bot
        self.redis = redis_client
        self.queue_dsn = queue_dsn or settings.QUEUE_DSN or settings.REDIS_DSN
        self.stream_key = settings.NOTIFY_STREAM_KEY
        self.running = False
        self.retry_config = RetryConfig(max_retries=3, initial_backoff=1.0, max_backoff=60.0)
        self.antispam = AntiSpam(redis_client)
        self.preferences = NotificationPreferences(redis_client)
        self.consumer_name = f"bot-{uuid.uuid4().hex[:8]}"
        self.queue: RedisStreamQueue | RabbitQueue | None = None
        self.buffers: dict[tuple[int, str], list[NotificationEvent]] = defaultdict(list)
        self.buffer_tasks: dict[tuple[int, str], asyncio.Task[None]] = {}

    async def _init_queue(self) -> None:
        if self.queue_dsn and self.queue_dsn.startswith("amqp"):
            self.queue = RabbitQueue(self.queue_dsn, self.stream_key)
        else:
            self.queue = RedisStreamQueue(
                redis_client=self.redis,
                stream_key=self.stream_key,
                group=settings.NOTIFY_CONSUMER_GROUP,
                consumer_name=self.consumer_name,
            )
        await self.queue.init()

    async def start(self) -> None:
        """Start consuming notifications."""
        self.running = True
        await self._init_queue()
        logger.info("Starting notification consumer (queue=%s)", self.queue_dsn or self.stream_key)

        while self.running:
            try:
                messages = await self.queue.read_batch() if self.queue else []
                if not messages:
                    await asyncio.sleep(0.1)
                    continue
                for message in messages:
                    await self._handle_message(message)
            except asyncio.CancelledError:
                logger.info("Notification consumer cancelled")
                break
            except Exception as exc:
                logger.error("Error in consumer loop: %s", exc, exc_info=True)
                await asyncio.sleep(2)

    async def stop(self) -> None:
        """Stop consuming notifications."""
        self.running = False
        for task in list(self.buffer_tasks.values()):
            task.cancel()
        self.buffer_tasks.clear()
        if self.queue:
            await self.queue.close()
        logger.info("Notification consumer stopped")

    async def _handle_message(self, message: QueueMessage) -> None:
        try:
            event = NotificationEvent.from_stream_fields(message.fields, fallback_id=message.raw_id)
        except Exception as exc:
            tg_notify_dropped_total.labels(reason="parse_error").inc()
            logger.warning("Failed to parse notification message %s: %s", message.raw_id, exc)
            await message.ack()
            return

        if event.type not in NOTIFICATION_EVENT_TYPES:
            tg_notify_dropped_total.labels(reason="unsupported_type").inc()
            logger.debug("Unsupported notification type %s", event.type)
            await message.ack()
            return

        if not await self.preferences.is_subscribed(event.chat_id):
            tg_notify_dropped_total.labels(reason="unsubscribed").inc()
            logger.debug("Chat %s unsubscribed from notifications", event.chat_id)
            await message.ack()
            return

        if await self.antispam.is_duplicate(event.chat_id, event.event_id):
            tg_notify_dropped_total.labels(reason="duplicate").inc()
            await message.ack()
            return

        if await self.antispam.check_daily_limit(event.chat_id):
            tg_notify_dropped_total.labels(reason="daily_limit").inc()
            await message.ack()
            return

        await self._enqueue(event)
        await message.ack()

    async def _enqueue(self, event: NotificationEvent) -> None:
        key = (event.chat_id, event.type)
        self.buffers[key].append(event)
        if key not in self.buffer_tasks:
            self.buffer_tasks[key] = asyncio.create_task(self._flush_after_delay(key))

    async def _flush_after_delay(self, key: tuple[int, str]) -> None:
        try:
            await asyncio.sleep(self.antispam.coalesce_window)
            await self._flush_now(key)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error("Failed to flush coalesced notifications for %s: %s", key, exc, exc_info=True)
        finally:
            self.buffer_tasks.pop(key, None)

    async def _flush_now(self, key: tuple[int, str]) -> None:
        events = self.buffers.pop(key, [])
        if not events:
            return

        chat_id, event_type = key
        quiet_now, delay = await self.preferences.is_quiet_now(chat_id)
        if quiet_now:
            # Reschedule after quiet window
            logger.info("Chat %s is in quiet hours, delaying %d events by %s sec", chat_id, len(events), delay)
            self.buffers[key] = events
            self.buffer_tasks[key] = asyncio.create_task(self._delayed_flush(key, max(delay, 5)))
            return

        first_ts = min((ev.get_timestamp() for ev in events), default=datetime.now(UTC))
        last_ts = max((ev.get_timestamp() for ev in events), default=first_ts)
        coalesced = CoalescedNotification(
            chat_id=chat_id,
            event_type=event_type,
            events=events,
            first_ts=first_ts,
            last_ts=last_ts,
        )

        await self._send_coalesced(coalesced)

    async def _delayed_flush(self, key: tuple[int, str], delay: int) -> None:
        try:
            await asyncio.sleep(delay)
            await self._flush_now(key)
        except asyncio.CancelledError:
            return
        finally:
            self.buffer_tasks.pop(key, None)

    async def _send_coalesced(self, notification: CoalescedNotification) -> None:
        chat_id = notification.chat_id
        try:
            if len(notification.events) == 1:
                event = notification.events[0]
                event_type = event.type
                text = await format_notification(event)

                # Special handling for download_allowed: generate one-time link
                if event_type == "download_allowed":
                    payload = event.payload or {}
                    cap_id = payload.get("capId")

                    if cap_id:
                        try:
                            # Generate one-time download link
                            dl_resp = await prepare_download(chat_id, cap_id)
                            download_url = dl_resp.url
                            ttl_minutes = dl_resp.ttl // 60

                            # Replace placeholder with actual URL
                            text = text.replace("{download_url}", download_url)

                            # Add TTL info if not already in message
                            if "{ttl}" in text:
                                text = text.replace("{ttl}", str(ttl_minutes))
                            else:
                                text += f"\n\n⏱ Link expires in {ttl_minutes} minutes"

                        except Exception as e:
                            logger.error(
                                "Failed to prepare download link for chat %s, capId %s: %s", chat_id, cap_id, e
                            )
                            # Fallback to error message
                            text = "❌ Failed to generate download link. Please try again later."
            else:
                text = await format_coalesced(notification)
                event_type = notification.event_type

            success = await send_with_retry(self.bot, chat_id, text, self.retry_config)
            if success:
                tg_notify_sent_total.labels(type=event_type).inc()
                logger.info(
                    "Sent notification to chat %s (type=%s, events=%d)",
                    chat_id,
                    event_type,
                    len(notification.events),
                )
            else:
                tg_notify_dropped_total.labels(reason="send_failed").inc()
                logger.warning(
                    "Failed to send notification to chat %s (type=%s, events=%d)",
                    chat_id,
                    event_type,
                    len(notification.events),
                )
        except Exception as exc:
            tg_notify_dropped_total.labels(reason="send_exception").inc()
            logger.error("Error sending notification to chat %s: %s", chat_id, exc, exc_info=True)
