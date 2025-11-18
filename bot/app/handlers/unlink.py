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
from aiohttp import ClientError, ClientSession

from ..config import settings

logger = logging.getLogger(__name__)

router = Router()


class UnlinkBackendError(Exception):
    """Ошибка при вызове DFSP API для unlink."""


async def _request_unlink(chat_id: int) -> None:
    """
    Вызывает DFSP API: DELETE /tg/link.

    Сейчас бэкенд не принимает chat_id в теле, но мы на будущее можем
    передавать его, если API расширят под бот.
    """
    api_url = str(settings.DFSP_API_URL).rstrip("/")

    headers: dict[str, str] = {}
    if settings.DFSP_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.DFSP_API_TOKEN}"

    try:
        async with ClientSession() as session:
            # Если когда-нибудь API будет принимать chat_id, можно добавить json={"chat_id": chat_id}
            async with session.delete(
                f"{api_url}/tg/link",
                headers=headers,
                timeout=5,
            ) as resp:
                if resp.status == 200:
                    # По контракту операция идемпотентна:
                    # даже если привязки уже нет, backend вернёт ok: true.
                    return

                text = await resp.text()
                logger.error("DFSP DELETE /tg/link failed: %s %s", resp.status, text)
                raise UnlinkBackendError()

    except ClientError as e:
        logger.exception("Failed to call DFSP API (unlink): %s", e)
        raise UnlinkBackendError() from e


async def _perform_unlink(
    chat_id: int,
    send: Callable[[str], Awaitable[None]],
) -> None:
    try:
        await _request_unlink(chat_id)
    except UnlinkBackendError:
        await send("😔 Сейчас не получается отвязать этот Telegram от аккаунта DFSP.\nПопробуй ещё раз чуть позже.")
        return

    await send(
        "🔓 Привязка этого Telegram к аккаунту DFSP отключена.\n\n"
        "Если захочешь вернуться, используй /link, чтобы привязать аккаунт снова."
    )


# --- /unlink командой ----------------------------------------------------------

CONFIRM_TEXT = (
    "Ты точно хочешь отвязать этот Telegram от своего DFSP аккаунта?\n\n"
    "Это действие можно будет отменить только новой привязкой через /link."
)

CONFIRM_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отвязать", callback_data="unlink:confirm"),
            InlineKeyboardButton(text="↩️ Отмена", callback_data="unlink:cancel"),
        ]
    ]
)


@router.message(Command("unlink"))
async def cmd_unlink(message: Message) -> None:
    await message.answer(CONFIRM_TEXT, reply_markup=CONFIRM_KB)


@router.callback_query(F.data == "unlink:start")
async def cb_unlink_start(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Что-то пошло не так, попробуй ещё раз.", show_alert=True)
        return

    await callback.message.answer(CONFIRM_TEXT, reply_markup=CONFIRM_KB)
    await callback.answer()


# --- Callback-кнопки -----------------------------------------------------------


@router.callback_query(F.data == "unlink:cancel")
async def cb_unlink_cancel(callback: CallbackQuery) -> None:
    # Просто закрываем "часики" и убираем клавиатуру
    await callback.answer("Отмена")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data == "unlink:confirm")
async def cb_unlink_confirm(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Что-то пошло не так, попробуй снова.", show_alert=True)
        return

    chat_id = callback.message.chat.id

    async def send(text: str) -> None:
        await callback.message.edit_text(text)

    await _perform_unlink(chat_id=chat_id, send=send)
    await callback.answer("✅ Аккаунт отвязан")

    # Показываем главное меню после отвязки
    from ..handlers import start as start_handlers

    keyboard = start_handlers.get_main_keyboard(is_linked=False)
    await callback.message.answer(start_handlers.START_TEXT_UNLINKED, reply_markup=keyboard)
