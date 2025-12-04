"""Обработчики для кнопок главного меню."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from ..handlers import files as files_handlers
from ..handlers import me as me_handlers
from ..handlers import notifications as notify_handlers
from ..handlers import switch as switch_handlers
from ..handlers import start as start_handlers
from ..services.message_store import get_message

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "menu:profile")
async def cb_menu_profile(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Мой профиль' из меню."""
    if not callback.message:
        await callback.answer(await get_message("common.missing_message"), show_alert=True)
        return

    # Переиспользуем логику /me на исходном сообщении, чтобы не терять bot-инстанс
    await me_handlers.cmd_me(callback.message)
    await callback.answer()


@router.callback_query(F.data == "menu:files")
async def cb_menu_files(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Мои файлы' из меню."""
    if not callback.message:
        await callback.answer(await get_message("common.missing_message"), show_alert=True)
        return

    # Переиспользуем логику /files на исходном сообщении, чтобы не терять bot-инстанс
    await files_handlers.cmd_files(callback.message)
    await callback.answer()


@router.callback_query(F.data == "menu:switch")
async def cb_menu_switch(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Сменить адрес' из меню."""
    if not callback.message:
        await callback.answer(await get_message("common.missing_message"), show_alert=True)
        return

    await switch_handlers.cmd_switch(callback.message)
    await callback.answer()


@router.callback_query(F.data == "menu:notify")
async def cb_menu_notify(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Уведомления' из меню."""
    if not callback.message:
        await callback.answer(await get_message("common.missing_message"), show_alert=True)
        return

    await notify_handlers.cmd_notify(callback.message)
    await callback.answer()


@router.callback_query(F.data == "menu:verify")
async def cb_menu_verify(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Проверить файл' из меню."""
    if not callback.message:
        await callback.answer(await get_message("common.missing_message"), show_alert=True)
        return

    # Показываем инструкцию с кнопкой для быстрого доступа к файлам
    files_btn = await get_message("buttons.get_file_id")
    home_btn = await get_message("buttons.home")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=files_btn, callback_data="menu:files"),
            ],
            [
                InlineKeyboardButton(text=home_btn, callback_data="menu:home"),
            ],
        ]
    )

    await callback.message.answer(
        await get_message("menu.verify_instructions"),
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "menu:home")
async def cb_menu_home(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Главное меню'."""
    if not callback.message:
        await callback.answer(await get_message("common.missing_message"), show_alert=True)
        return

    from ..services.dfsp_api import get_bot_profile

    # Проверяем статус привязки
    chat_id = callback.message.chat.id
    is_linked = False
    try:
        profile = await get_bot_profile(chat_id)
        is_linked = profile is not None
    except Exception as exc:
        logger.debug("Failed to get bot profile for chat_id=%s: %s", chat_id, exc)

    keyboard = await start_handlers.get_main_keyboard(is_linked=is_linked)
    start_text = await start_handlers.get_start_text(is_linked=is_linked)
    await callback.message.answer(start_text, reply_markup=keyboard)
    await callback.answer()
