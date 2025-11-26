from __future__ import annotations

import logging
import re

import httpx
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import settings

router = Router(name="verify")
logger = logging.getLogger(__name__)


def validate_file_id(file_id: str) -> str | None:
    """
    Валидирует fileId и приводит к формату 0x + 64 hex символа.

    Принимает:
    - С префиксом 0x: "0x1234..." (должно быть 66 символов)
    - Без префикса: "1234..." (должно быть 64 hex символа)

    Returns:
        Нормализованный file_id в формате 0x + 64 hex или None если невалидный
    """
    if not file_id:
        return None

    file_id = file_id.strip()

    # Проверяем формат с 0x
    if file_id.startswith("0x"):
        hex_part = file_id[2:]
        if len(file_id) == 66 and re.match(r"^[0-9a-fA-F]{64}$", hex_part):
            return file_id.lower()
        return None

    # Проверяем формат без 0x (64 hex символа)
    if re.match(r"^[0-9a-fA-F]{64}$", file_id):
        return f"0x{file_id.lower()}"

    return None


@router.message(Command("verify"))
async def cmd_verify(message: Message) -> None:
    """
    Обработчик команды /verify <fileId>.

    Валидация: hex32 (с 0x или без).
    Показывает короткую сводку + ссылку на полную проверку.
    """
    chat_id = message.chat.id
    logger.info("Handling /verify for chat_id=%s", chat_id)

    # Извлекаем fileId из команды
    command_text = message.text or ""
    parts = command_text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "❌ Не указан ID файла.\n\n"
            "Использование: `/verify <fileId>`\n\n"
            "Пример:\n"
            "`/verify 0x1234567890abcdef...`\n"
            "или\n"
            "`/verify 1234567890abcdef...`",
            parse_mode="Markdown",
        )
        return

    file_id_input = parts[1]
    file_id = validate_file_id(file_id_input)

    if not file_id:
        await message.answer(
            "❌ Неверный формат ID файла.\n\n"
            "ID должен быть:\n"
            "• 64 hex символа с префиксом `0x` (66 символов всего)\n"
            "• или 64 hex символа без префикса\n\n"
            "Пример: `0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef`",
            parse_mode="Markdown",
        )
        return

    # Вызываем API для верификации
    try:
        api_url = str(settings.DFSP_API_URL).rstrip("/")
        url = f"{api_url}/bot/verify/{file_id}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)

        if resp.status_code == 404:
            await message.answer(
                f"❌ Файл с ID `{file_id[:20]}...` не найден.",
                parse_mode="Markdown",
            )
            return

        if resp.status_code == 400:
            await message.answer(
                "❌ Неверный формат ID файла.",
                parse_mode="Markdown",
            )
            return

        resp.raise_for_status()
        data = resp.json()

        onchain_ok = data.get("onchain_ok", False)
        offchain_ok = data.get("offchain_ok", False)
        match = data.get("match", False)
        last_anchor_tx = data.get("lastAnchorTx")

        # Формируем короткую сводку
        status_icon = "✅" if match else "❌"
        status_text = "совпадает" if match else "не совпадает"

        summary = (
            f"{status_icon} *Результат верификации файла*\n\n"
            f"On-chain: {'✅' if onchain_ok else '❌'}\n"
            f"Off-chain: {'✅' if offchain_ok else '❌'}\n"
            f"Совпадение: {status_text}"
        )

        if last_anchor_tx:
            summary += f"\n\nПоследняя транзакция: `{last_anchor_tx[:20]}...`"

        # Формируем URL для полной проверки
        origin = str(settings.PUBLIC_WEB_ORIGIN).rstrip("/")
        full_verify_url = f"{origin}/verify/{file_id}"

        # Создаем кнопку "Открыть полную проверку" и "Главное меню"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Открыть полную проверку", url=full_verify_url)],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")],
            ]
        )

        await message.answer(summary, reply_markup=keyboard, parse_mode="Markdown")

    except httpx.HTTPStatusError as e:
        logger.exception("Failed to verify file: HTTP error")
        await message.answer(
            f"❌ Ошибка при проверке файла: {e.response.status_code}",
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Failed to verify file")
        await message.answer(
            "❌ Не удалось проверить файл.\nПопробуй ещё раз чуть позже.",
            parse_mode="Markdown",
        )
