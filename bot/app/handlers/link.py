# bot/app/handlers/link.py
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiohttp import ClientSession, ClientError

from ..config import settings

logger = logging.getLogger(__name__)

router = Router()


class BackendError(Exception):
    """Общая ошибка DFSP API."""


class RateLimitError(Exception):
    def __init__(self, retry_after: str | None = None):
        self.retry_after = retry_after


async def _request_link_token(chat_id: int) -> tuple[str, str | None]:
    """
    Дёргаем DFSP API: POST /tg/link-start { chat_id }

    :return: (link_token, expires_at)
    """
    api_url = str(settings.DFSP_API_URL).rstrip("/")

    headers: dict[str, str] = {}
    # На будущее: если для сервисных ручек нужен токен
    if settings.DFSP_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.DFSP_API_TOKEN}"

    try:
        async with ClientSession() as session:
            async with session.post(
                f"{api_url}/tg/link-start",
                json={"chat_id": chat_id},
                headers=headers,
                timeout=5,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["link_token"], data.get("expires_at")

                if resp.status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    raise RateLimitError(retry_after=retry_after)

                # Логируем тело, чтобы проще было дебажить
                text = await resp.text()
                logger.error(
                    "DFSP /tg/link-start failed: %s %s", resp.status, text
                )
                raise BackendError()

    except ClientError as e:
        logger.exception("Failed to call DFSP API: %s", e)
        raise BackendError() from e


def _build_link_keyboard(deep_link: str) -> InlineKeyboardMarkup | None:
    if "localhost" in deep_link:
        return None  # не делаем кнопку для локалки

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Открыть DFSP", url=deep_link)]
        ]
    )



async def _send_link(
    chat_id: int,
    send: Callable[[str, InlineKeyboardMarkup | None], Awaitable[None]],
) -> None:
    try:
        link_token, expires_at = await _request_link_token(chat_id)
    except RateLimitError as e:
        seconds: int | None = None
        if e.retry_after and e.retry_after.isdigit():
            seconds = int(e.retry_after)

        if seconds and seconds > 0:
            text = (
                "⚠️ Слишком часто запрашиваешь ссылку.\n"
                f"Попробуй снова примерно через {seconds} секунд."
            )
        else:
            text = (
                "⚠️ Слишком часто запрашиваешь ссылку.\n"
                "Попробуй ещё раз чуть позже."
            )
        await send(text, None)
        return
    except BackendError:
        await send(
            "😔 Сейчас не получается сгенерировать ссылку на привязку.\n"
            "Попробуй ещё раз чуть позже.",
            None,
        )
        return

    origin = str(settings.PUBLIC_WEB_ORIGIN).rstrip("/")
    deep_link = f"{origin}/tg/link?token={link_token}"

    text = (
        "Вот ссылка для привязки аккаунта DFSP к этому Telegram.\n\n"
        "Ссылка одноразовая и действует ограниченное время. "
        "Если она истечёт, просто вызови /link ещё раз."
    )
    
    kb = _build_link_keyboard(deep_link)
    text = (
        "Вот ссылка для привязки аккаунта DFSP к этому Telegram.\n\n"
        f"{deep_link}\n\n"
        "Ссылка одноразовая и действует ограниченное время. "
        "Если она истечёт, просто вызови /link ещё раз."
    )
    await send(text, kb)



# --- /link командой ------------------------------------------------------------


@router.message(Command("link"))
async def cmd_link(message: Message) -> None:
    await _send_link(
        chat_id=message.chat.id,
        send=lambda text, kb: message.answer(text, reply_markup=kb),
    )


# --- Кнопка "🔗 Привязать аккаунт" из /start -----------------------------------


@router.callback_query(F.data == "link:start")
async def cb_link_start(callback: CallbackQuery) -> None:
    # На всякий случай: если апдейт пришёл не из лички
    if not callback.message:
        await callback.answer(
            "Напиши мне в личку, чтобы привязать аккаунт.", show_alert=True
        )
        return

    await _send_link(
        chat_id=callback.message.chat.id,
        send=lambda text, kb: callback.message.answer(
            text, reply_markup=kb
        ),
    )
    # Закрываем "часики" у пользователя
    await callback.answer()
