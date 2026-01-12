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
    """Selects the starting text from the message store based on the linking status."""
    key = "start.linked" if is_linked else "start.unlinked"
    return await get_message(key, language=language)


async def get_main_keyboard(is_linked: bool = False) -> InlineKeyboardMarkup:
    """Creates the main menu with buttons depending on the linking status."""
    profile_btn = await get_message("buttons.profile")
    files_btn = await get_message("buttons.files")
    switch_btn = await get_message("buttons.switch")
    notify_btn = await get_message("buttons.notify")
    unlink_btn = await get_message("buttons.unlink")
    link_btn = await get_message("buttons.link")
    home_btn = await get_message("buttons.home")

    keyboard_buttons = []

    if is_linked:
        # If the account is linked - show all functions
        keyboard_buttons = [
            [
                InlineKeyboardButton(text=profile_btn, callback_data="menu:profile"),
                InlineKeyboardButton(text=files_btn, callback_data="menu:files"),
            ],
            [
                InlineKeyboardButton(text=switch_btn, callback_data="menu:switch"),
                InlineKeyboardButton(text=notify_btn, callback_data="menu:notify"),
                InlineKeyboardButton(text=unlink_btn, callback_data="unlink:start"),
            ],
            [
                InlineKeyboardButton(text=home_btn, callback_data="menu:home"),
            ],
        ]
    else:
        # If the account is not linked - show linking
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


# Deprecated constant, use get_main_keyboard() instead


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Handler for the /start command with a dynamic menu."""
    chat_id = message.chat.id

    # Check linking status
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
    """Handler for the /help command."""
    chat_id = message.chat.id

    # Check linking status
    is_linked = False
    try:
        profile = await get_bot_profile(chat_id)
        is_linked = profile is not None
    except Exception:
        logger.debug("Failed to check profile status for chat_id=%s", chat_id)

    help_text = await get_message("start.help")

    keyboard = await get_main_keyboard(is_linked=is_linked)
    await message.answer(help_text, reply_markup=keyboard)
