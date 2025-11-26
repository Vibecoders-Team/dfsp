"""Anti-spam mechanisms for notifications."""

import logging
from datetime import UTC, datetime

from redis import asyncio as aioredis

logger = logging.getLogger(__name__)


class AntiSpam:
    """Anti-spam protection for notifications."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client
        self.dedup_ttl = 86400  # 1 day
        self.coalesce_window = 60  # 60 seconds
        self.daily_limit = 100  # max notifications per day per chat
        self.daily_limit_soft = 50  # after this, start digest mode

    async def is_duplicate(self, event_id: str) -> bool:
        """
        Check if event_id was already processed (deduplication).

        Returns True if duplicate, False if new.
        """
        key = f"notif:dedup:{event_id}"
        try:
            exists = await self.redis.exists(key)
            if exists:
                return True

            # Mark as seen
            await self.redis.setex(key, self.dedup_ttl, "1")
            return False
        except Exception as e:
            logger.warning("Failed to check deduplication: %s", e)
            # On error, allow processing (fail open)
            return False

    async def should_coalesce(self, chat_id: int, event_type: str, event_ts: datetime) -> bool:
        """
        Check if event should be coalesced (grouped with others).

        Returns True if should wait for coalescing, False if send immediately.
        """
        window_key = f"notif:coalesce:{chat_id}:{event_type}"
        try:
            # Get last event timestamp in window
            last_ts_str = await self.redis.get(window_key)
            if last_ts_str:
                last_ts = datetime.fromisoformat(last_ts_str.decode())
                age = (event_ts - last_ts).total_seconds()
                if age < self.coalesce_window:
                    # Update window timestamp
                    await self.redis.setex(
                        window_key,
                        self.coalesce_window,
                        event_ts.isoformat(),
                    )
                    return True

            # Set new window
            await self.redis.setex(window_key, self.coalesce_window, event_ts.isoformat())
            return False
        except Exception as e:
            logger.warning("Failed to check coalescing: %s", e)
            return False

    async def check_daily_limit(self, chat_id: int) -> tuple[bool, bool]:
        """
        Check daily notification limits.

        Returns:
            (should_drop, use_digest)
            - should_drop: True if should drop notification (hard limit exceeded)
            - use_digest: True if should use digest mode (soft limit exceeded)
        """
        today = datetime.now(UTC).date().isoformat()
        key = f"notif:daily:{chat_id}:{today}"

        try:
            count_str = await self.redis.get(key)
            count = int(count_str) if count_str else 0

            if count >= self.daily_limit:
                return (True, True)  # Drop (hard limit)

            if count >= self.daily_limit_soft:
                # Increment and return digest mode
                await self.redis.incr(key)
                await self.redis.expire(key, 86400)  # 1 day
                return (False, True)  # Use digest

            # Increment counter
            await self.redis.incr(key)
            await self.redis.expire(key, 86400)
            return (False, False)  # Normal mode
        except Exception as e:
            logger.warning("Failed to check daily limit: %s", e)
            # On error, allow processing (fail open)
            return (False, False)

    async def get_coalesced_events(self, chat_id: int, event_type: str) -> list[str]:
        """
        Get coalesced event IDs for a chat/type.

        Returns list of event_id strings.
        """
        queue_key = f"notif:queue:{chat_id}:{event_type}"
        try:
            events = await self.redis.lrange(queue_key, 0, -1)
            return [e.decode() for e in events]
        except Exception as e:
            logger.warning("Failed to get coalesced events: %s", e)
            return []

    async def add_to_coalesce_queue(self, chat_id: int, event_type: str, event_id: str) -> None:
        """Add event to coalesce queue."""
        queue_key = f"notif:queue:{chat_id}:{event_type}"
        try:
            await self.redis.rpush(queue_key, event_id)
            await self.redis.expire(queue_key, self.coalesce_window + 10)
        except Exception as e:
            logger.warning("Failed to add to coalesce queue: %s", e)

    async def clear_coalesce_queue(self, chat_id: int, event_type: str) -> None:
        """Clear coalesce queue after sending."""
        queue_key = f"notif:queue:{chat_id}:{event_type}"
        try:
            await self.redis.delete(queue_key)
        except Exception as e:
            logger.warning("Failed to clear coalesce queue: %s", e)
