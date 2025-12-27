"""Обработчик callback после успешной привязки кошелька через веб."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from ..handlers import me as me_handlers
from ..handlers import start as start_handlers
from ..services.message_store import get_message

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("link:success"))
async def cb_link_success(callback: CallbackQuery) -> None:
    """Обработчик callback после успешной привязки."""
    if not callback.message:
        await callback.answer(await get_message("common.missing_message"), show_alert=True)
        return

    await callback.answer(await get_message("link.success_alert"), show_alert=True)

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
    keyboard = await start_handlers.get_main_keyboard(is_linked=True)
    await callback.message.answer(
        await get_message("link.success_menu_prompt"),
        reply_markup=keyboard,
    )
