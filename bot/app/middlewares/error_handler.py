from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, Update

from ..utils.format import mask_chat_id

logger = logging.getLogger(__name__)


def _get_chat_id(event: Update) -> int | None:
    if event.message:
        return event.message.chat.id
    if event.callback_query and event.callback_query.message:
        return event.callback_query.message.chat.id
    return None


class ErrorHandlerMiddleware(BaseMiddleware):
    """
    Ловим все исключения, логируем с trace-id + маской chat_id,
    в чат отдаём дружелюбный текст без деталей.
    """

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        trace_id = data.get("trace_id")
        chat_id = _get_chat_id(event)
        masked_chat = mask_chat_id(chat_id)

        try:
            return await handler(event, data)
        except Exception as exc:
            logger.exception(
                "Unhandled error while processing update (trace=%s chat=%s): %s",
                trace_id,
                masked_chat,
                exc,
            )

            # Не пытаемся слать ответ в заведомо несуществующий чат
            if isinstance(exc, TelegramBadRequest) and "chat not found" in str(exc):
                return None

            text = "Ой, что-то пошло не так 🤕\nМы уже смотрим, попробуйте ещё раз чуть позже."  # noqa: RUF001

            # старательно, но аккуратно отвечаем пользователю
            if event.message and isinstance(event.message, Message):
                try:
                    await event.message.answer(text)
                except TelegramBadRequest:
                    pass
            elif event.callback_query and isinstance(event.callback_query, CallbackQuery):
                try:
                    await event.callback_query.answer(text, show_alert=True)
                except TelegramBadRequest:
                    pass

            return None
