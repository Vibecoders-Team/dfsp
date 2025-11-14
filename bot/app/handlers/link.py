from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("link"))
async def cmd_link(message: Message) -> None:
    await message.answer(
        "Привязка аккаунта ещё в разработке 🔧\n"
        "Скоро здесь появится ссылка и инструкции по связыванию Telegram с DFSP."
    )
