from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

START_TEXT = (
    "Привет! Я DFSP бот 👋\n\n"
    "Я помогу привязать твой Telegram к аккаунту DFSP, а потом — смотреть файлы "
    "и права доступа (grants), не заходя в веб.\n\n"
    "🔐 <b>Приватность</b>\n"
    "• Файлы шифруются на клиенте, бот и сервер видят только метаданные.\n"
    "• Мы храним твой Telegram chat_id и события только для безопасности и аудита.\n\n"
    "Чтобы начать, нажми кнопку ниже и привяжи аккаунт."
)

START_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔗 Привязать аккаунт",
                callback_data="link:start",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔓 Отвязать аккаунт",
                callback_data="unlink:start",
            )
        ],
    ]
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(START_TEXT, reply_markup=START_KEYBOARD)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    help_text = (
        "Я DFSP бот.\n\n"
        "Основные команды:\n"
        "• /start — приветствие и привязка аккаунта\n"
        "• /link — начать привязку Telegram к DFSP\n\n"
        "Нажми “🔗 Привязать аккаунт” под приветствием, чтобы запустить привязку."
    )
    await message.answer(help_text, reply_markup=START_KEYBOARD)
