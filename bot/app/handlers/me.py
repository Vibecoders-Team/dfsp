# app/handlers/me.py
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..services.dfsp_api import get_bot_profile
from ..services.message_store import get_message

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
        await message.answer(await get_message("profile.fetch_error"))
        return

    if profile is None:
        # 404 от API — чат не привязан
        from .start import get_main_keyboard

        keyboard = await get_main_keyboard(is_linked=False)
        await message.answer(await get_message("profile.not_linked"), reply_markup=keyboard)
        return

    masked = mask_address(profile.address)
    display_name = profile.display_name or await get_message("profile.no_name")

    from .start import get_main_keyboard

    text = (
        await get_message(
            "profile.details",
            variables={"display_name": display_name, "address": masked},
        )
    )

    keyboard = await get_main_keyboard(is_linked=True)
    await message.answer(text, reply_markup=keyboard)
