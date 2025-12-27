"""Anti-spam mechanisms for notifications."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from redis import asyncio as aioredis

from ...config import settings

logger = logging.getLogger(__name__)


class AntiSpam:
    """Ограничения: идемпотентность, дневные лимиты и контроль окна коалесинга."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client
        self.seen_ttl = 86400  # 1 day
        self.coalesce_window = settings.NOTIFY_COALESCE_WINDOW_SEC
        self.daily_limit = settings.NOTIFY_DAILY_MAX

    async def is_duplicate(self, chat_id: int, event_id: str) -> bool:
        """
        Проверяет, обрабатывали ли уже событие для чата.

        Хранит set `tg:event:seen:<chat_id>` c TTL=1 день.
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
        Инкрементирует дневной счётчик и говорит, превысили ли лимит.

        Возвращает True, если нужно дропнуть событие.
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
