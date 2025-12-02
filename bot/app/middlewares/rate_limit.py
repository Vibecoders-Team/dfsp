from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, Update

try:
    from redis import asyncio as aioredis  # type: ignore[import]
except Exception:  # на всякий, если пакета нет
    aioredis = None  # type: ignore[assignment]

from ..config import settings
from ..services.message_store import get_message
from ..utils.format import mask_chat_id

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Простой in-memory лимитер по ключу (chat_id).
    Алгоритм: фиксированное окно с reset.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # key -> (count, reset_at_ts)
        self._buckets: dict[int, tuple[int, float]] = {}

    def check(self, key: int, *, now: float | None = None) -> tuple[bool, float]:
        """
        :return: (allowed, retry_after_seconds)
        """
        if now is None:
            now = time.time()

        count, reset_at = self._buckets.get(key, (0, 0.0))

        if now >= reset_at:
            # новое окно
            count = 0
            reset_at = now + self.window_seconds

        if count >= self.max_requests:
            retry_after = max(0.0, reset_at - now)
            return False, retry_after

        count += 1
        self._buckets[key] = (count, reset_at)
        return True, 0.0


class RateLimitMiddleware(BaseMiddleware):
    """
    Лимит по чатам:
      - in-memory RateLimiter всегда
      - + Redis-ключи, если QUEUE_DSN=redis://...
    """

    def __init__(
        self,
        max_requests: int = 5,
        window_seconds: int = 2,
    ) -> None:
        super().__init__()
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._limiter = RateLimiter(max_requests, window_seconds)

        self._redis_dsn: str | None = None
        self._redis = None

        if settings.QUEUE_DSN and settings.QUEUE_DSN.startswith("redis://"):
            self._redis_dsn = settings.QUEUE_DSN

    async def _ensure_redis(self) -> None:
        if self._redis_dsn and self._redis is None and aioredis is not None:
            self._redis = await aioredis.from_url(  # type: ignore[call-arg]
                self._redis_dsn,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("RateLimitMiddleware: connected to Redis at %s", self._redis_dsn)

    async def _check_rate_limit(self, chat_id: int) -> tuple[bool, float]:
        # если Redis доступен — используем его, иначе чисто in-memory
        if self._redis_dsn:
            await self._ensure_redis()

        if self._redis is None:
            return self._limiter.check(chat_id)

        key = f"tg:rl:{chat_id}"
        # INCR + EXPIRE — стандартный паттерн rate-limit в Redis
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, self.window_seconds)

        if count > self.max_requests:
            ttl = await self._redis.ttl(key)
            retry_after = float(ttl) if ttl and ttl > 0 else float(self.window_seconds)
            return False, retry_after

        return True, 0.0

    @staticmethod
    def _get_chat_id(event: Update) -> int | None:
        if event.message:
            return event.message.chat.id
        if event.callback_query and event.callback_query.message:
            return event.callback_query.message.chat.id
        return None

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        chat_id = self._get_chat_id(event)
        if chat_id is None:
            return await handler(event, data)

        allowed, retry_after = await self._check_rate_limit(chat_id)

        if allowed:
            return await handler(event, data)

        masked = mask_chat_id(chat_id)
        logger.info(
            "Rate limit hit for chat %s (retry_after=%.1fs)",
            masked,
            retry_after,
        )

        # Ответ в чат
        retry_seconds = max(1, round(retry_after))
        text = await get_message("rate_limit.hit", variables={"retry_seconds": retry_seconds})

        if event.message and isinstance(event.message, Message):
            await event.message.answer(text)
        elif event.callback_query and isinstance(event.callback_query, CallbackQuery):
            # можно show_alert=True, но это уже вкусовщина
            await event.callback_query.answer(text, show_alert=True)

        # не передаём управление дальше
        return None
