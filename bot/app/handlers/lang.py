from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

try:
    from redis import asyncio as aioredis  # type: ignore[import]
except Exception:  # pragma: no cover
    aioredis = None  # type: ignore[assignment]

from app.config import settings
from app.security.hmac import sign, verify
from app.services.message_store import get_message, reset_current_language, set_current_language

router = Router(name="lang")
logger = logging.getLogger(__name__)

LANG_OPTIONS = {
    "ru": "Русский",
    "en": "English",
}

CALLBACK_SECRET = settings.CALLBACK_HMAC_SECRET or settings.WEBHOOK_SECRET
CALLBACK_TTL = 300  # 5 минут достаточно для выбора языка
CALLBACK_SIG_BYTES = 5  # короткая подпись для 64-байтного лимита

_redis = None


async def _ensure_redis() -> None:
    global _redis
    if _redis or not settings.REDIS_DSN or aioredis is None:
        return
    try:
        _redis = await aioredis.from_url(  # type: ignore[call-arg]
            settings.REDIS_DSN,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Lang: connected to Redis at %s", settings.REDIS_DSN)
    except Exception as exc:  # pragma: no cover
        logger.warning("Lang: failed to connect Redis %s: %s", settings.REDIS_DSN, exc)
        _redis = None


async def _get_lang(chat_id: int) -> str:
    if settings.REDIS_DSN:
        await _ensure_redis()
    if _redis is None:
        return settings.I18N_FALLBACK or settings.BOT_DEFAULT_LANGUAGE

    key = f"tg:lang:{chat_id}"
    try:
        lang = await _redis.get(key)
    except Exception as exc:  # pragma: no cover
        logger.warning("Lang: failed to read lang for %s: %s", chat_id, exc)
        return settings.I18N_FALLBACK or settings.BOT_DEFAULT_LANGUAGE

    if lang in LANG_OPTIONS:
        return lang
    return settings.I18N_FALLBACK or settings.BOT_DEFAULT_LANGUAGE


async def _set_lang(chat_id: int, lang: str) -> bool:
    if settings.REDIS_DSN:
        await _ensure_redis()
    if _redis is None:
        return False

    key = f"tg:lang:{chat_id}"
    try:
        await _redis.set(key, lang)
        return True
    except Exception as exc:  # pragma: no cover
        logger.warning("Lang: failed to store lang for %s: %s", chat_id, exc)
        return False


def _make_callback(chat_id: int, lang: str) -> str:
    payload = {
        "c": "l",
        "lang": lang,
        "ts": int(time.time()),
    }
    secret = f"{CALLBACK_SECRET}:{chat_id}"
    signed = sign(
        payload,
        secret,
        ttl_seconds=CALLBACK_TTL,
        signature_bytes=CALLBACK_SIG_BYTES,
    )
    return f"lang:{signed}"


def _parse_callback(data: str | None, chat_id: int | None) -> dict[str, Any] | None:
    if not data or not data.startswith("lang:") or chat_id is None:
        return None
    token = data.split("lang:", 1)[1]
    secret = f"{CALLBACK_SECRET}:{chat_id}"
    payload = verify(
        token,
        secret,
        ttl_seconds=CALLBACK_TTL,
        signature_bytes=CALLBACK_SIG_BYTES,
    )
    if not payload or payload.get("c") != "l":
        return None
    return payload


def _lang_label(lang: str) -> str:
    return LANG_OPTIONS.get(lang, lang)


def _lang_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Русский", callback_data=_make_callback(chat_id, "ru"))],
            [InlineKeyboardButton(text="English", callback_data=_make_callback(chat_id, "en"))],
        ]
    )


async def _send_with_lang(
    lang: str,
    send: Callable[[str, InlineKeyboardMarkup | None], Awaitable[Any]],
    key: str,
    variables: dict[str, Any] | None = None,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    token = set_current_language(lang)
    try:
        text = await get_message(key, variables=variables)
    finally:
        reset_current_language(token)
    await send(text, keyboard)


@router.message(Command("lang"))
async def cmd_lang(message: Message) -> None:
    chat_id = message.chat.id
    current = await _get_lang(chat_id)
    kb = _lang_keyboard(chat_id)
    await _send_with_lang(
        current,
        lambda text, keyboard: message.answer(text, reply_markup=keyboard),
        "lang.prompt",
        {"current": _lang_label(current)},
        kb,
    )


@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id if callback.message else None
    if chat_id is None:
        await callback.answer(await get_message("common.no_chat"), show_alert=True)
        return

    payload = _parse_callback(callback.data, chat_id)
    if not payload:
        await callback.answer(await get_message("lang.invalid_callback"), show_alert=True)
        return

    lang = payload.get("lang")
    if lang not in LANG_OPTIONS:
        await callback.answer(await get_message("lang.invalid_callback"), show_alert=True)
        return

    stored = await _set_lang(chat_id, lang)
    if not stored:
        await callback.answer(await get_message("common.retry_later"), show_alert=True)
        return

    async def send(text: str, keyboard: InlineKeyboardMarkup | None) -> None:
        if callback.message:
            await callback.message.edit_text(text, reply_markup=keyboard)

    await _send_with_lang(
        lang,
        send,
        "lang.changed",
        {"lang": _lang_label(lang)},
        _lang_keyboard(chat_id),
    )
    await callback.answer()
