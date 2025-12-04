from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
import httpx

from ..config import settings
from ..services.message_store import get_message

logger = logging.getLogger(__name__)

router = Router()


class UnlinkBackendError(Exception):
    """Ошибка при вызове DFSP API для unlink."""


class NotLinkedError(Exception):
    """Аккаунт ещё не привязан к Telegram."""


async def _request_unlink(chat_id: int) -> None:
    """
    Вызывает DFSP API: удаляет все связи через /bot/links/{address}.
    """
    api_url = str(settings.DFSP_API_URL).rstrip("/")

    headers: dict[str, str] = {"X-TG-Chat-Id": str(chat_id)}
    if settings.DFSP_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.DFSP_API_TOKEN}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            links_resp = await client.get(f"{api_url}/bot/links", headers=headers)
            if links_resp.status_code == 404:
                raise NotLinkedError()

            links_resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("DFSP GET /bot/links failed: %s %s", links_resp.status_code, links_resp.text)
            raise UnlinkBackendError() from exc
        except httpx.HTTPError as exc:
            logger.exception("Failed to call DFSP API (unlink list): %s", exc)
            raise UnlinkBackendError() from exc

        links = links_resp.json().get("links") or []
        if not links:
            raise NotLinkedError()

        for link in links:
            address = link.get("address")
            if not address:
                continue
            try:
                resp = await client.delete(f"{api_url}/bot/links/{address}", headers=headers)
            except httpx.HTTPError as exc:
                logger.exception("Failed to call DFSP API (unlink): %s", exc)
                raise UnlinkBackendError() from exc

            if resp.status_code in (200, 404):
                continue

            logger.error("DFSP DELETE /bot/links/%s failed: %s %s", address, resp.status_code, resp.text)
            raise UnlinkBackendError()


async def _perform_unlink(
    chat_id: int,
    send: Callable[[str], Awaitable[None]],
) -> bool:
    try:
        await _request_unlink(chat_id)
    except NotLinkedError:
        await send(await get_message("profile.not_linked"))
        return False
    except UnlinkBackendError:
        await send(await get_message("unlink.backend_error"))
        return False

    await send(await get_message("unlink.success"))
    return True


# --- /unlink командой ----------------------------------------------------------

async def build_unlink_confirm_keyboard() -> InlineKeyboardMarkup:
    yes_btn = await get_message("buttons.unlink_confirm_yes")
    cancel_btn = await get_message("buttons.cancel")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=yes_btn, callback_data="unlink:confirm"),
                InlineKeyboardButton(text=cancel_btn, callback_data="unlink:cancel"),
            ]
        ]
    )


@router.message(Command("unlink"))
async def cmd_unlink(message: Message) -> None:
    confirm_kb = await build_unlink_confirm_keyboard()
    await message.answer(await get_message("unlink.confirm"), reply_markup=confirm_kb)


@router.callback_query(F.data == "unlink:start")
async def cb_unlink_start(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer(await get_message("common.retry_later"), show_alert=True)
        return

    confirm_kb = await build_unlink_confirm_keyboard()
    await callback.message.answer(await get_message("unlink.confirm"), reply_markup=confirm_kb)
    await callback.answer()


# --- Callback-кнопки -----------------------------------------------------------


@router.callback_query(F.data == "unlink:cancel")
async def cb_unlink_cancel(callback: CallbackQuery) -> None:
    # Просто закрываем "часики" и убираем клавиатуру
    await callback.answer(await get_message("unlink.cancelled"))
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data == "unlink:confirm")
async def cb_unlink_confirm(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer(await get_message("common.retry_later"), show_alert=True)
        return

    chat_id = callback.message.chat.id

    async def send(text: str) -> None:
        await callback.message.edit_text(text)

    success = await _perform_unlink(chat_id=chat_id, send=send)
    if not success:
        await callback.answer()
        return

    await callback.answer(await get_message("unlink.confirmed"))

    # Показываем главное меню после отвязки
    from ..handlers import start as start_handlers

    keyboard = await start_handlers.get_main_keyboard(is_linked=False)
    start_text = await start_handlers.get_start_text(is_linked=False)
    await callback.message.answer(start_text, reply_markup=keyboard)
