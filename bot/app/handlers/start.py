from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


HELP_TEXT = (
    "Привет! Я DFSP бот.\n\n"
    "/start — начать\n"
    "/help — показать это сообщение\n"
)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
