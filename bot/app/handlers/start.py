from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..services.dfsp_api import get_bot_profile
from ..services.message_store import get_message

router = Router()
logger = logging.getLogger(__name__)

async def get_start_text(is_linked: bool, language: str | None = None) -> str:
    """Выбирает стартовый текст из хранилища сообщений по статусу привязки."""
    key = "start.linked" if is_linked else "start.unlinked"
    return await get_message(key, language=language)


async def get_main_keyboard(is_linked: bool = False) -> InlineKeyboardMarkup:
    """Создаёт главное меню с кнопками в зависимости от статуса привязки."""
    profile_btn = await get_message("buttons.profile")
    files_btn = await get_message("buttons.files")
    unlink_btn = await get_message("buttons.unlink")
    link_btn = await get_message("buttons.link")
    home_btn = await get_message("buttons.home")

    keyboard_buttons = []

    if is_linked:
        # Если аккаунт привязан - показываем все функции
        keyboard_buttons = [
            [
                InlineKeyboardButton(text=profile_btn, callback_data="menu:profile"),
                InlineKeyboardButton(text=files_btn, callback_data="menu:files"),
            ],
            [
                InlineKeyboardButton(text=unlink_btn, callback_data="unlink:start"),
            ],
            [
                InlineKeyboardButton(text=home_btn, callback_data="menu:home"),
            ],
        ]
    else:
        # Если аккаунт не привязан - показываем привязку
        keyboard_buttons = [
            [
                InlineKeyboardButton(
                    text=link_btn,
                    callback_data="link:start",
                )
            ],
            [
                InlineKeyboardButton(text=home_btn, callback_data="menu:home"),
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

    keyboard = await get_main_keyboard(is_linked=is_linked)
    start_text = await get_start_text(is_linked=is_linked)
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

    help_text = await get_message("start.help")

    keyboard = await get_main_keyboard(is_linked=is_linked)
    await message.answer(help_text, reply_markup=keyboard)
