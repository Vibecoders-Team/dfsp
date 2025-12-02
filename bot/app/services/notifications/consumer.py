"""Notification consumer for Redis queue."""

import asyncio
import json
import logging

from aiogram import Bot
from redis import asyncio as aioredis

from ...metrics import tg_notify_dropped_total, tg_notify_sent_total
from .address_resolver import AddressResolver
from .antispam import AntiSpam
from .formatter import format_coalesced, format_notification
from .models import CoalescedNotification, NotificationEvent
from .retry import RetryConfig, send_with_retry

logger = logging.getLogger(__name__)

# Event types we care about
NOTIFICATION_EVENT_TYPES = {
    "grant_created",
    "grant_received",
    "grant_revoked",
    "download_allowed",
    "download_denied",
    "anchor_ok",
    "relayer_warn",
}


class NotificationConsumer:
    """Consumer for notification events from Redis queue."""

    def __init__(
        self,
        bot: Bot,
        redis_client: aioredis.Redis,
        queue_key: str = "events:queue",
    ) -> None:
        self.bot = bot
        self.redis = redis_client
        self.queue_key = queue_key
        self.address_resolver = AddressResolver(redis_client)
        self.antispam = AntiSpam(redis_client)
        self.running = False
        self.retry_config = RetryConfig(
            max_retries=3,
            initial_backoff=1.0,
            max_backoff=60.0,
        )

    async def start(self) -> None:
        """Start consuming notifications."""
        self.running = True
        logger.info("Starting notification consumer for queue: %s", self.queue_key)

        while self.running:
            try:
                await self._consume_batch()
            except asyncio.CancelledError:
                logger.info("Consumer cancelled")
                break
            except Exception as e:
                logger.error("Error in consumer loop: %s", e, exc_info=True)
                await asyncio.sleep(5)  # Backoff on error

    async def stop(self) -> None:
        """Stop consuming notifications."""
        self.running = False
        logger.info("Stopping notification consumer")

    async def _consume_batch(self) -> None:
        """Consume a batch of events from queue."""
        try:
            # Blocking pop with timeout (BLPOP)
            result = await self.redis.blpop(self.queue_key, timeout=1)
            if not result:
                return  # Timeout, no events

            _, event_json = result
            event_data = json.loads(event_json.decode())

            # Parse event
            try:
                event = NotificationEvent.model_validate(event_data)
            except Exception as e:
                logger.warning("Failed to parse event: %s, error: %s", event_data, e)
                return

            # Filter by event type
            if event.type not in NOTIFICATION_EVENT_TYPES:
                return  # Skip unknown event types

            # Process event
            await self._process_event(event)

        except Exception as e:
            logger.error("Unexpected error in consume_batch: %s", e, exc_info=True)
            await asyncio.sleep(1)

    async def _process_event(self, event: NotificationEvent) -> None:
        """Process a single notification event."""
        # Deduplication check
        if await self.antispam.is_duplicate(event.event_id):
            logger.debug("Skipping duplicate event: %s", event.event_id)
            tg_notify_dropped_total.labels(reason="duplicate").inc()
            return

        # Resolve chat_id from address
        chat_id = await self.address_resolver.resolve_from_event(event)
        if not chat_id:
            logger.debug(
                "No chat_id found for event %s (subject: %s)",
                event.event_id,
                event.subject,
            )
            tg_notify_dropped_total.labels(reason="no_chat_id").inc()
            return

        # Check daily limits
        should_drop, use_digest = await self.antispam.check_daily_limit(chat_id)
        if should_drop:
            logger.debug(
                "Dropping notification for chat %d (daily limit exceeded)",
                chat_id,
            )
            tg_notify_dropped_total.labels(reason="daily_limit_exceeded").inc()
            return

        event_ts = event.get_timestamp()

        # Check if should coalesce
        should_coalesce = await self.antispam.should_coalesce(chat_id, event.type, event_ts)

        if should_coalesce and use_digest:
            # Add to coalesce queue
            await self.antispam.add_to_coalesce_queue(chat_id, event.type, event.event_id)
            logger.debug(
                "Added event %s to coalesce queue for chat %d",
                event.event_id,
                chat_id,
            )
            return

        # Send immediately or process coalesced
        if should_coalesce:
            # Wait a bit and check for more events
            await asyncio.sleep(2)
            await self._send_coalesced(chat_id, event.type, event)
        else:
            # Send immediately
            await self._send_single(chat_id, event)

    async def _send_single(self, chat_id: int, event: NotificationEvent) -> None:
        """Send a single notification."""
        try:
            text = await format_notification(event)
            success = await send_with_retry(self.bot, chat_id, text, self.retry_config)
            if success:
                tg_notify_sent_total.labels(type=event.type).inc()
                logger.info(
                    "Sent notification %s to chat %d (type: %s)",
                    event.event_id,
                    chat_id,
                    event.type,
                )
            else:
                tg_notify_dropped_total.labels(reason="send_failed").inc()
                logger.warning(
                    "Failed to send notification %s to chat %d",
                    event.event_id,
                    chat_id,
                )
        except Exception as e:
            tg_notify_dropped_total.labels(reason="send_exception").inc()
            logger.error(
                "Error sending notification %s to chat %d: %s",
                event.event_id,
                chat_id,
                e,
                exc_info=True,
            )

    async def _send_coalesced(self, chat_id: int, event_type: str, latest_event: NotificationEvent) -> None:
        """Send coalesced notification (multiple events grouped)."""
        try:
            # Get coalesced event IDs
            event_ids = await self.antispam.get_coalesced_events(chat_id, event_type)
            if not event_ids:
                # No coalesced events, send single
                await self._send_single(chat_id, latest_event)
                return

            # TODO: Fetch full events from Redis/queue by event_id
            # For now, we'll create a simple coalesced notification
            # In production, you'd want to store full event data

            # Create coalesced notification
            coalesced = CoalescedNotification(
                chat_id=chat_id,
                event_type=event_type,
                events=[latest_event],  # Simplified - would include all events
                first_ts=latest_event.get_timestamp(),
                last_ts=latest_event.get_timestamp(),
            )

            text = await format_coalesced(coalesced)
            success = await send_with_retry(self.bot, chat_id, text, self.retry_config)

            if success:
                tg_notify_sent_total.labels(type=event_type).inc()
                logger.info(
                    "Sent coalesced notification to chat %d (%d events, type: %s)",
                    chat_id,
                    len(event_ids) + 1,
                    event_type,
                )
                # Clear coalesce queue
                await self.antispam.clear_coalesce_queue(chat_id, event_type)
            else:
                tg_notify_dropped_total.labels(reason="coalesced_send_failed").inc()
                logger.warning("Failed to send coalesced notification to chat %d", chat_id)
        except Exception as e:
            logger.error(
                "Error sending coalesced notification to chat %d: %s",
                chat_id,
                e,
                exc_info=True,
            )
