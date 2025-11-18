from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Update

from ..utils.format import mask_chat_id

logger = logging.getLogger(__name__)


def _get_chat_id(event: Update) -> int | None:
    if event.message:
        return event.message.chat.id
    if event.callback_query and event.callback_query.message:
        return event.callback_query.message.chat.id
    return None


def _get_update_kind(event: Update) -> str:
    if event.message:
        return "message"
    if event.callback_query:
        return "callback_query"
    if event.inline_query:
        return "inline_query"
    return "update"


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        trace_id = uuid.uuid4().hex[:8]
        data["trace_id"] = trace_id

        chat_id = _get_chat_id(event)
        masked_chat = mask_chat_id(chat_id)
        kind = _get_update_kind(event)

        logger.info(
            "trace=%s kind=%s chat=%s",
            trace_id,
            kind,
            masked_chat,
        )

        return await handler(event, data)
