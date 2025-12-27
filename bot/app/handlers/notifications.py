from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from redis import asyncio as aioredis

from ..config import settings
from ..services.message_store import get_message
from ..services.notifications.preferences import NotificationPreferences, QuietHours

router = Router()

_redis: aioredis.Redis | None = None
DEFAULT_QUIET = QuietHours(start_min=23 * 60, end_min=7 * 60)


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_DSN, decode_responses=False)
    return _redis


async def _render_status(prefs: NotificationPreferences, chat_id: int) -> str:
    subscribed = await prefs.is_subscribed(chat_id)
    quiet = await prefs.get_quiet_hours(chat_id)

    title = await get_message("notify.title")
    status_key = "notify.status.enabled" if subscribed else "notify.status.disabled"
    status_line = await get_message(status_key)

    quiet_line_key = "notify.status.quiet_on" if quiet else "notify.status.quiet_off"
    variables: dict[str, Any] = {}
    if quiet:
        variables["window"] = quiet.serialize()
    quiet_line = await get_message(quiet_line_key, variables=variables or None)

    return f"{title}\n{status_line}\n{quiet_line}"


async def _build_keyboard(prefs: NotificationPreferences, chat_id: int) -> InlineKeyboardMarkup:
    subscribed = await prefs.is_subscribed(chat_id)
    notify_toggle = (
        InlineKeyboardButton(text=await get_message("buttons.notify_off"), callback_data="notify:off")
        if subscribed
        else InlineKeyboardButton(text=await get_message("buttons.notify_on"), callback_data="notify:on")
    )
    quiet_row = [
        InlineKeyboardButton(text=await get_message("buttons.quiet_default"), callback_data="notify:quiet:default"),
        InlineKeyboardButton(text=await get_message("buttons.quiet_off"), callback_data="notify:quiet:off"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[[notify_toggle], quiet_row])


async def _refresh_view(message: Message, prefs: NotificationPreferences) -> None:
    text = await _render_status(prefs, message.chat.id)
    keyboard = await _build_keyboard(prefs, message.chat.id)
    await message.edit_text(text, reply_markup=keyboard)


@router.message(Command("notify"))
async def cmd_notify(message: Message) -> None:
    if not message.chat:
        await message.answer(await get_message("common.no_chat"))
        return

    prefs = NotificationPreferences(await _get_redis())
    text = await _render_status(prefs, message.chat.id)
    keyboard = await _build_keyboard(prefs, message.chat.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "notify:on")
async def cb_notify_on(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer(await get_message("common.retry_later"), show_alert=True)
        return

    prefs = NotificationPreferences(await _get_redis())
    await prefs.set_subscribed(callback.message.chat.id, True)
    await _refresh_view(callback.message, prefs)
    await callback.answer(await get_message("notify.changed.on"))


@router.callback_query(F.data == "notify:off")
async def cb_notify_off(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer(await get_message("common.retry_later"), show_alert=True)
        return

    prefs = NotificationPreferences(await _get_redis())
    await prefs.set_subscribed(callback.message.chat.id, False)
    await _refresh_view(callback.message, prefs)
    await callback.answer(await get_message("notify.changed.off"))


@router.callback_query(F.data == "notify:quiet:default")
async def cb_quiet_default(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer(await get_message("common.retry_later"), show_alert=True)
        return

    prefs = NotificationPreferences(await _get_redis())
    await prefs.set_quiet_hours(callback.message.chat.id, DEFAULT_QUIET)
    await _refresh_view(callback.message, prefs)
    await callback.answer(await get_message("notify.changed.quiet_on", variables={"window": DEFAULT_QUIET.serialize()}))


@router.callback_query(F.data == "notify:quiet:off")
async def cb_quiet_off(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer(await get_message("common.retry_later"), show_alert=True)
        return

    prefs = NotificationPreferences(await _get_redis())
    await prefs.clear_quiet_hours(callback.message.chat.id)
    await _refresh_view(callback.message, prefs)
    await callback.answer(await get_message("notify.changed.quiet_off"))
