# app/handlers/me.py
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..services.dfsp_api import get_bot_profile

router = Router(name="profile_me")
logger = logging.getLogger(__name__)


def mask_address(addr: str) -> str:
    """
    Маскируем адрес вида 0x1234567890abcdef... в 0x1234…cdef.
    """
    if not addr:
        return addr

    addr = addr.strip()
    if len(addr) <= 10:
        return addr

    return f"{addr[:6]}…{addr[-4:]}"


@router.message(Command("me"))
async def cmd_me(message: Message) -> None:
    chat_id = message.chat.id
    logger.info("Handling /me for chat_id=%s", chat_id)

    try:
        logger.info("Calling DFSP /bot/me for chat_id=%s", chat_id)
        profile = await get_bot_profile(chat_id)
        logger.info("DFSP /bot/me result: %r", profile)
    except Exception:
        logger.exception("Failed to get bot profile from DFSP")
        await message.answer("😔 Не удалось получить профиль.\nПопробуй ещё раз чуть позже.")
        return

    if profile is None:
        # 404 от API — чат не привязан
        from .start import get_main_keyboard

        keyboard = get_main_keyboard(is_linked=False)
        await message.answer(
            "❌ К этому чату ещё не привязан кошелёк.\n\n"
            "Чтобы привязать кошелёк:\n"
            "1. Нажми кнопку «🔗 Привязать аккаунт» ниже\n"
            "2. Открой ссылку в браузере\n"
            "3. Войди и подпиши сообщение своим кошельком.",
            reply_markup=keyboard,
        )
        return

    masked = mask_address(profile.address)
    display_name = profile.display_name or "без имени"

    from .start import get_main_keyboard

    text = (
        "👤 <b>Твой профиль</b>\n\n"
        f"Имя: <b>{display_name}</b>\n"
        f"Адрес: <code>{masked}</code>\n\n"
        "Если хочешь отвязать текущий кошелёк — используй команду /unlink.\n"
        "Чтобы привязать другой кошелёк:\n"
        "1. Сначала /unlink\n"
        "2. Затем снова /link и пройди привязку с новым адресом."
    )

    keyboard = get_main_keyboard(is_linked=True)
    await message.answer(text, reply_markup=keyboard)
