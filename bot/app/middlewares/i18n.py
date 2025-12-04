from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, Update

try:
    from redis import asyncio as aioredis  # type: ignore[import]
except Exception:  # pragma: no cover
    aioredis = None  # type: ignore[assignment]

from app.config import settings
from app.services.message_store import reset_current_language, set_current_language

logger = logging.getLogger(__name__)


class I18nMiddleware(BaseMiddleware):
    """
    Определяет язык чата (Redis key tg:lang:<chat_id>), ставит его в контекст для message_store.
    Фолбэк — settings.BOT_DEFAULT_LANGUAGE.
    """

    def __init__(self, fallback: str | None = None) -> None:
        super().__init__()
        self.fallback = fallback or settings.BOT_DEFAULT_LANGUAGE
        self._redis_dsn: str | None = settings.REDIS_DSN
        self._redis = None

    async def _ensure_redis(self) -> None:
        if self._redis or not self._redis_dsn or aioredis is None:
            return
        try:
            self._redis = await aioredis.from_url(  # type: ignore[call-arg]
                self._redis_dsn,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("I18nMiddleware: connected to Redis at %s", self._redis_dsn)
        except Exception as exc:  # pragma: no cover
            logger.warning("I18nMiddleware: failed to connect to Redis %s: %s", self._redis_dsn, exc)
            self._redis = None

    @staticmethod
    def _get_chat_id(event: Update) -> int | None:
        if event.message:
            return event.message.chat.id
        if event.callback_query and event.callback_query.message:
            return event.callback_query.message.chat.id
        return None

    async def _get_language(self, chat_id: int) -> str:
        if self._redis_dsn:
            await self._ensure_redis()
        if self._redis is None:
            return self.fallback

        key = f"tg:lang:{chat_id}"
        try:
            lang = await self._redis.get(key)
        except Exception as exc:  # pragma: no cover
            logger.warning("I18nMiddleware: failed to read lang for %s: %s", chat_id, exc)
            return self.fallback

        if lang in ("ru", "en"):
            return lang
        return self.fallback

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        chat_id = self._get_chat_id(event)
        token = None

        if chat_id is not None:
            lang = await self._get_language(chat_id)
            data["lang"] = lang
            token = set_current_language(lang)

        try:
            return await handler(event, data)
        finally:
            if token is not None:
                reset_current_language(token)
