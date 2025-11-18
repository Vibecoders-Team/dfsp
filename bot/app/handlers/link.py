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


def _build_link_keyboard(deep_link: str) -> InlineKeyboardMarkup | None:
    if "localhost" in deep_link:
        return None  # не делаем кнопку для локалки

    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 Открыть DFSP", url=deep_link)]])


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
            text = f"⚠️ Слишком часто запрашиваешь ссылку.\nПопробуй снова примерно через {seconds} секунд."
        else:
            text = "⚠️ Слишком часто запрашиваешь ссылку.\nПопробуй ещё раз чуть позже."
        await send(text, None)
        return
    except BackendError:
        await send(
            "😔 Сейчас не получается сгенерировать ссылку на привязку.\nПопробуй ещё раз чуть позже.",
            None,
        )
        return

    origin = str(settings.PUBLIC_WEB_ORIGIN).rstrip("/")
    deep_link = f"{origin}/tg/link?token={link_token}"

    # Проверка на потенциальные проблемы с конфигурацией
    from ..utils.diagnostics import check_public_web_origin

    is_valid, error_msg = check_public_web_origin()

    text = (
        "Вот ссылка для привязки аккаунта DFSP к этому Telegram.\n\n"
        f"🔗 {deep_link}\n\n"
        "Ссылка одноразовая и действует ограниченное время. "
        "Если она истечёт, просто вызови /link ещё раз."
    )

    if not is_valid:
        text += f"\n\n⚠️ {error_msg}"

    # Показываем кнопку только для валидного origin
    kb = _build_link_keyboard(deep_link) if is_valid else None

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
        await callback.answer("Напиши мне в личку, чтобы привязать аккаунт.", show_alert=True)
        return

    await _send_link(
        chat_id=callback.message.chat.id,
        send=lambda text, kb: callback.message.answer(text, reply_markup=kb),
    )
    # Закрываем "часики" у пользователя
    await callback.answer()

    # После отправки ссылки показываем инструкцию
    await callback.message.answer(
        "📋 <b>Инструкция по привязке:</b>\n\n"
        "1. Нажми на ссылку выше или скопируй её\n"
        "2. Открой ссылку в браузере\n"
        "3. Войди в свой кошелёк\n"
        "4. Подпиши сообщение для подтверждения\n\n"
        "После успешной привязки ты получишь уведомление, и сможешь использовать все функции бота!"
    )

    # Обновляем главное меню
    from ..handlers import start as start_handlers

    keyboard = start_handlers.get_main_keyboard(is_linked=False)
    await callback.message.answer(
        "💡 <b>Главное меню</b>\n\nИспользуй кнопки ниже для навигации:", reply_markup=keyboard
    )
