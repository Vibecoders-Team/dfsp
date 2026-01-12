"""Anti-spam mechanisms for notifications."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from redis import asyncio as aioredis

from ...config import settings

logger = logging.getLogger(__name__)


class AntiSpam:
    """Restrictions: idempotency, daily limits, and coalescing window control."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client
        self.seen_ttl = 86400  # 1 day
        self.coalesce_window = settings.NOTIFY_COALESCE_WINDOW_SEC
        self.daily_limit = settings.NOTIFY_DAILY_MAX

    async def is_duplicate(self, chat_id: int, event_id: str) -> bool:
        """
        Checks if an event has already been processed for the chat.

        Stores a set `tg:event:seen:<chat_id>` with TTL=1 day.
        """
        key = f"tg:event:seen:{chat_id}"
        try:
            added = await self.redis.sadd(key, event_id)
            if added and added > 0:
                await self.redis.expire(key, self.seen_ttl)
            return added == 0
        except Exception as exc:
            logger.warning("Failed to check deduplication: %s", exc)
            return False

    async def check_daily_limit(self, chat_id: int, weight: int = 1) -> bool:
        """
        Increments the daily counter and indicates if the limit has been exceeded.

        Returns True if the event should be dropped.
        """
        today = date.today().isoformat()
        key = f"tg:daily:{chat_id}:{today}"
        try:
            new_value = await self.redis.incrby(key, weight)
            await self.redis.expire(key, int(timedelta(days=2).total_seconds()))
            return new_value > self.daily_limit
        except Exception as exc:
            logger.warning("Failed to update daily limit: %s", exc)
            return False
