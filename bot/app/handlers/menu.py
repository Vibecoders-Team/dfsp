"""Обработчики для кнопок главного меню."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from ..handlers import files as files_handlers
from ..handlers import me as me_handlers

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "menu:profile")
async def cb_menu_profile(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Мой профиль' из меню."""
    if not callback.message:
        await callback.answer("Ошибка: не удалось определить сообщение.", show_alert=True)
        return

    # Переиспользуем логику /me на исходном сообщении, чтобы не терять bot-инстанс
    await me_handlers.cmd_me(callback.message)
    await callback.answer("✅ Профиль загружен")


@router.callback_query(F.data == "menu:files")
async def cb_menu_files(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Мои файлы' из меню."""
    if not callback.message:
        await callback.answer("Ошибка: не удалось определить сообщение.", show_alert=True)
        return

    # Переиспользуем логику /files на исходном сообщении, чтобы не терять bot-инстанс
    await files_handlers.cmd_files(callback.message)
    await callback.answer("✅ Список файлов загружен")


@router.callback_query(F.data == "menu:verify")
async def cb_menu_verify(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Проверить файл' из меню."""
    if not callback.message:
        await callback.answer("Ошибка: не удалось определить сообщение.", show_alert=True)
        return

    # Показываем инструкцию с кнопкой для быстрого доступа к файлам
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📁 Получить fileId из списка", callback_data="menu:files"),
            ],
            [
                InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu:home"),
            ],
        ]
    )

    await callback.message.answer(
        "🔍 <b>Проверка файла</b>\n\n"
        "Чтобы проверить файл, отправь команду:\n"
        "<code>/verify &lt;fileId&gt;</code>\n\n"
        "Пример:\n"
        "<code>/verify 0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef</code>\n\n"
        "💡 <b>Совет:</b> Нажми кнопку ниже, чтобы получить fileId из списка файлов",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "menu:home")
async def cb_menu_home(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Главное меню'."""
    if not callback.message:
        await callback.answer("Ошибка: не удалось определить сообщение.", show_alert=True)
        return

    from ..handlers.start import START_TEXT_LINKED, START_TEXT_UNLINKED, get_main_keyboard
    from ..services.dfsp_api import get_bot_profile

    # Проверяем статус привязки
    chat_id = callback.message.chat.id
    is_linked = False
    try:
        profile = await get_bot_profile(chat_id)
        is_linked = profile is not None
    except Exception as exc:
        logger.debug("Failed to get bot profile for chat_id=%s: %s", chat_id, exc)

    keyboard = get_main_keyboard(is_linked=is_linked)
    start_text = START_TEXT_LINKED if is_linked else START_TEXT_UNLINKED
    await callback.message.answer(start_text, reply_markup=keyboard)
    await callback.answer("🏠 Главное меню")
