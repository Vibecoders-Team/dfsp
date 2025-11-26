"""Обработчик callback после успешной привязки кошелька через веб."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from ..handlers import me as me_handlers
from ..handlers import start as start_handlers

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("link:success"))
async def cb_link_success(callback: CallbackQuery) -> None:
    """Обработчик callback после успешной привязки."""
    if not callback.message:
        await callback.answer("Ошибка: не удалось определить сообщение.", show_alert=True)
        return

    await callback.answer("✅ Аккаунт успешно привязан!", show_alert=True)

    # Показываем профиль автоматически
    fake_message = Message(
        message_id=callback.message.message_id,
        date=callback.message.date,
        chat=callback.message.chat,
        from_user=callback.from_user,
        text="/me",
    )

    # Показываем профиль автоматически после привязки
    await me_handlers.cmd_me(fake_message)

    # Показываем главное меню с доступными функциями
    keyboard = start_handlers.get_main_keyboard(is_linked=True)
    await callback.message.answer(
        "✅ <b>Отлично! Теперь ты можешь использовать все функции бота!</b>\n\nВыбери действие из меню ниже:",
        reply_markup=keyboard,
    )
