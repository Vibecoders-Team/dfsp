from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..services.dfsp_api import get_bot_profile

router = Router()
logger = logging.getLogger(__name__)

START_TEXT_LINKED = (
    "👋 <b>Добро пожаловать в DFSP бот!</b>\n\n"
    "Твой аккаунт привязан. Используй кнопки ниже для быстрого доступа к функциям.\n\n"
    "🔐 <b>Приватность</b>\n"
    "• Файлы шифруются на клиенте\n"
    "• Бот видит только метаданные"
)

START_TEXT_UNLINKED = (
    "👋 <b>Добро пожаловать в DFSP бот!</b>\n\n"
    "Я помогу привязать твой Telegram к аккаунту DFSP, а потом — смотреть файлы "
    "и права доступа (grants), не заходя в веб.\n\n"
    "🔐 <b>Приватность</b>\n"
    "• Файлы шифруются на клиенте, бот и сервер видят только метаданные.\n"
    "• Мы храним твой Telegram chat_id и события только для безопасности и аудита.\n\n"
    "Чтобы начать, нажми кнопку ниже и привяжи аккаунт."
)


def get_main_keyboard(is_linked: bool = False) -> InlineKeyboardMarkup:
    """Создаёт главное меню с кнопками в зависимости от статуса привязки."""
    keyboard_buttons = []

    if is_linked:
        # Если аккаунт привязан - показываем все функции
        keyboard_buttons = [
            [
                InlineKeyboardButton(text="👤 Мой профиль", callback_data="menu:profile"),
                InlineKeyboardButton(text="📁 Мои файлы", callback_data="menu:files"),
            ],
            [
                InlineKeyboardButton(text="🔓 Отвязать аккаунт", callback_data="unlink:start"),
            ],
            [
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home"),
            ],
        ]
    else:
        # Если аккаунт не привязан - показываем привязку
        keyboard_buttons = [
            [
                InlineKeyboardButton(
                    text="🔗 Привязать аккаунт",
                    callback_data="link:start",
                )
            ],
            [
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home"),
            ],
        ]

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


# Устаревшая константа, используем get_main_keyboard() вместо неё


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обработчик команды /start с динамическим меню."""
    chat_id = message.chat.id

    # Проверяем статус привязки
    is_linked = False
    try:
        profile = await get_bot_profile(chat_id)
        is_linked = profile is not None
    except Exception:
        logger.debug("Failed to check profile status for chat_id=%s", chat_id)

    keyboard = get_main_keyboard(is_linked=is_linked)
    start_text = START_TEXT_LINKED if is_linked else START_TEXT_UNLINKED
    await message.answer(start_text, reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Обработчик команды /help."""
    chat_id = message.chat.id

    # Проверяем статус привязки
    is_linked = False
    try:
        profile = await get_bot_profile(chat_id)
        is_linked = profile is not None
    except Exception:
        logger.debug("Failed to check profile status for chat_id=%s", chat_id)

    help_text = (
        "📖 <b>Справка по командам DFSP бота</b>\n\n"
        "🔹 <b>Основные команды:</b>\n"
        "• /start — главное меню\n"
        "• /me — мой профиль\n"
        "• /files — список моих файлов\n"
        "• /verify &lt;fileId&gt; — проверить файл\n"
        "• /link — привязать аккаунт\n"
        "• /unlink — отвязать аккаунт\n\n"
        "💡 <b>Совет:</b> Используй кнопки меню для быстрого доступа к функциям!"
    )

    keyboard = get_main_keyboard(is_linked=is_linked)
    await message.answer(help_text, reply_markup=keyboard)
