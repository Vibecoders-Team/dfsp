# bot/app/handlers/link.py
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
from ..services.message_store import get_message

logger = logging.getLogger(__name__)

router = Router()


class BackendError(Exception):
    """Общая ошибка DFSP API."""


class RateLimitError(Exception):
    def __init__(self, retry_after: str | None = None) -> None:
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
                logger.error("DFSP /tg/link-start failed: %s %s", resp.status, text)
                raise BackendError()

    except ClientError as e:
        logger.exception("Failed to call DFSP API: %s", e)
        raise BackendError() from e


async def _build_link_keyboard(deep_link: str) -> InlineKeyboardMarkup | None:
    if "localhost" in deep_link:
        return None  # не делаем кнопку для локалки

    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=await get_message("buttons.open_dfsp"), url=deep_link)]]
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
            text = await get_message("link.rate_limit_seconds", variables={"seconds": seconds})
        else:
            text = await get_message("link.rate_limit_generic")
        await send(text, None)
        return
    except BackendError:
        await send(await get_message("link.backend_error"), None)
        return

    origin = str(settings.PUBLIC_WEB_ORIGIN).rstrip("/")
    deep_link = f"{origin}/tg/link?token={link_token}"

    # Проверка на потенциальные проблемы с конфигурацией
    from ..utils.diagnostics import check_public_web_origin

    is_valid, error_msg = check_public_web_origin()

    diagnostic_note = f"\n\n⚠️ {error_msg}" if not is_valid and error_msg else ""
    kb = await _build_link_keyboard(deep_link) if is_valid else None
    if kb:
        text = await get_message("link.deep_link_button", variables={"diagnostic": diagnostic_note})
    else:
        text = await get_message(
            "link.deep_link",
            variables={"link_url": deep_link, "diagnostic": diagnostic_note},
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
        await callback.answer(await get_message("link.private_chat_required"), show_alert=True)
        return

    await _send_link(
        chat_id=callback.message.chat.id,
        send=lambda text, kb: callback.message.answer(text, reply_markup=kb),
    )
    # Закрываем "часики" у пользователя
    await callback.answer()
