from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..handlers.me import mask_address
from ..services.dfsp_api import BotLink, get_bot_links, switch_bot_link
from ..services.message_store import get_message

router = Router(name="switch")
logger = logging.getLogger(__name__)


async def _build_keyboard(links: list[BotLink]) -> InlineKeyboardMarkup:
    """Клавиатура с выбором адреса."""
    rows = []
    for link in links:
        prefix = "✅ " if link.is_active else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{mask_address(link.address)}",
                    callback_data=f"switch:{link.address.lower()}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=await get_message("buttons.home"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _summarize_links(links: list[BotLink]) -> str:
    active = next((link.address for link in links if link.is_active), None)
    total = len(links)
    if active:
        return f"{mask_address(active)} / {total}"
    return str(total)


async def _render_switch(message: Message, links: list[BotLink]) -> None:
    keyboard = await _build_keyboard(links)
    summary = _summarize_links(links)
    text = await get_message("switch.choose", variables={"summary": summary})
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("switch"))
async def cmd_switch(message: Message) -> None:
    """Команда /switch — выбор активного адреса."""
    chat_id = message.chat.id
    try:
        links = await get_bot_links(chat_id)
    except Exception:
        logger.exception("Failed to load links for chat_id=%s", chat_id)
        await message.answer(await get_message("switch.fetch_error"))
        return

    if not links:
        from .start import get_main_keyboard

        keyboard = await get_main_keyboard(is_linked=False)
        await message.answer(await get_message("profile.not_linked"), reply_markup=keyboard)
        return

    active_count = sum(1 for link in links if link.is_active)
    if len(links) == 1 and active_count == 1:
        await message.answer(
            await get_message("switch.only_one", variables={"address": mask_address(links[0].address)})
        )
        return

    await _render_switch(message, links)


@router.callback_query(F.data.startswith("switch:"))
async def cb_switch(callback: CallbackQuery) -> None:
    """Переключение активного адреса по кнопке."""
    if not callback.message:
        await callback.answer(await get_message("common.missing_message"), show_alert=True)
        return

    chat_id = callback.message.chat.id
    address = callback.data.split(":", 1)[1] if callback.data else ""
    if not address:
        await callback.answer(await get_message("switch.fetch_error"), show_alert=True)
        return

    try:
        ok = await switch_bot_link(chat_id, address)
    except Exception:
        logger.exception("Failed to switch link for chat_id=%s", chat_id)
        await callback.answer(await get_message("switch.switch_error"), show_alert=True)
        return

    if not ok:
        await callback.answer(await get_message("switch.not_found"), show_alert=True)
        return

    # перерисуем список
    try:
        links = await get_bot_links(chat_id)
    except Exception:
        links = None

    await callback.answer(await get_message("switch.success"))
    if links:
        await _render_switch(callback.message, links)
    else:
        await callback.message.answer(
            await get_message("switch.switch_info", variables={"address": mask_address(address)})
        )
