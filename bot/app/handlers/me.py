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
        await message.answer(
            "😔 Не удалось получить профиль.\n"
            "Попробуй ещё раз чуть позже."
        )
        return

    if profile is None:
        # 404 от API — чат не привязан
        await message.answer(
            "К этому чату ещё не привязан кошелёк.\n\n"
            "Чтобы привязать кошелёк:\n"
            "1. Нажми /link\n"
            "2. Открой ссылку в браузере\n"
            "3. Войди и подпиши сообщение своим кошельком."
        )
        return

    masked = mask_address(profile.address)
    display_name = profile.display_name or "без имени"

    text = (
        "👤 *Твой профиль*\n"
        f"Имя: *{display_name}*\n"
        f"Адрес: `{masked}`\n\n"
        "Если хочешь отвязать текущий кошелёк — используй команду /unlink.\n"
        "Чтобы привязать другой кошелёк:\n"
        "1. Сначала /unlink\n"
        "2. Затем снова /link и пройди привязку с новым адресом."
    )

    await message.answer(text, parse_mode="Markdown")
