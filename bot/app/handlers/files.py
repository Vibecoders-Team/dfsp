from __future__ import annotations

import logging
import secrets
import time

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..config import settings
from ..security.hmac import sign, verify
from ..services.dfsp_api import BotFile, get_bot_files
from ..services.message_store import get_message

router = Router(name="files")
logger = logging.getLogger(__name__)

# Короткие токены + HMAC для callback'ов (чтобы уложиться в лимит 64 байта)
CALLBACK_SECRET = settings.WEBHOOK_SECRET
CALLBACK_TTL = 60  # секунд
CALLBACK_SIG_BYTES = 6  # укороченная подпись для компактности
CALLBACK_PREFIX = "f:"  # чтобы не пересекаться с другими callback'ами
_CALLBACK_CACHE: dict[str, tuple[dict, float]] = {}


def _make_token() -> str:
    # 6 urlsafe символов, чтобы уместиться в 64-байтный лимит
    return secrets.token_urlsafe(4)  # ~6 chars


def _store_payload(data: dict, *, now: float | None = None) -> str:
    """Сохраняет payload в памяти и возвращает короткий токен."""
    token = _make_token()
    ts = now if now is not None else time.time()
    _CALLBACK_CACHE[token] = (data, ts)
    # лёгкая очистка протухших записей
    expired = [k for k, (_, t) in _CALLBACK_CACHE.items() if ts - t > CALLBACK_TTL]
    for k in expired:
        _CALLBACK_CACHE.pop(k, None)
    return token


def _get_payload(token: str) -> dict | None:
    item = _CALLBACK_CACHE.get(token)
    if not item:
        return None
    data, ts = item
    if time.time() - ts > CALLBACK_TTL:
        _CALLBACK_CACHE.pop(token, None)
        return None
    return data


def _make_callback(cmd: str, payload: dict) -> str:
    """
    Сохраняет подробный payload в кэше и возвращает подписанный компактный callback_data.
    Формат callback_data: base64url({"c": <cmd_code>, "t": <token>, "ts": <ts>}).HMAC
    cmd_code: o=open, v=verify, p=page
    """
    now = time.time()
    token = _store_payload(payload | {"cmd": cmd}, now=now)
    cmd_code = {"open": "o", "verify": "v", "page": "p"}.get(cmd, cmd[:1])
    signed = sign(
        {"c": cmd_code, "t": token, "ts": int(now)},
        CALLBACK_SECRET,
        ttl_seconds=CALLBACK_TTL,
        signature_bytes=CALLBACK_SIG_BYTES,
    )
    return f"{CALLBACK_PREFIX}{signed}"


def format_file_size(size: int) -> str:
    """Форматирует размер файла в читаемый вид."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def format_file_list(files: list[BotFile], header: str, item_template: str, empty_text: str) -> str:
    """Форматирует список файлов для отображения."""
    if not files:
        return empty_text

    lines = [header]
    for i, file in enumerate(files, 1):
        size_str = format_file_size(file.size)
        lines.append(
            item_template.format(
                index=i,
                name=file.name,
                size=size_str,
                updated=file.updatedAt[:10],  # Только дата
            )
        )

    return "\n".join(lines)


async def build_files_keyboard(
    files: list[BotFile],
    cursor: str | None = None,
    prev_cursor: str | None = None,
) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру с кнопками для файлов и пагинацией."""
    open_btn = await get_message("buttons.open")
    verify_btn = await get_message("buttons.verify")
    back_btn = await get_message("buttons.back")
    next_btn = await get_message("buttons.next")
    home_btn = await get_message("buttons.home")
    buttons = []

    # Кнопки для каждого файла: "Открыть" и "Verify"
    for file in files:
        file_id = file.id_hex

        open_payload = _make_callback("open", {"file_id": file_id})
        verify_payload = _make_callback("verify", {"file_id": file_id})

        buttons.append(
            [
                InlineKeyboardButton(text=open_btn, callback_data=open_payload),
                InlineKeyboardButton(text=verify_btn, callback_data=verify_payload),
            ]
        )

    # Кнопки пагинации
    nav_buttons = []
    if prev_cursor:  # Есть предыдущая страница
        prev_payload = _make_callback("page", {"cursor": prev_cursor})
        nav_buttons.append(InlineKeyboardButton(text=back_btn, callback_data=prev_payload))

    if cursor:  # Есть следующая страница
        next_payload = _make_callback("page", {"cursor": cursor})
        nav_buttons.append(InlineKeyboardButton(text=next_btn, callback_data=next_payload))

    if nav_buttons:
        buttons.append(nav_buttons)

    # Добавляем кнопку "Главное меню"
    buttons.append(
        [
            InlineKeyboardButton(text=home_btn, callback_data="menu:home"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("files"))
async def cmd_files(message: Message) -> None:
    """Обработчик команды /files."""
    chat_id = message.chat.id
    logger.info("Handling /files for chat_id=%s", chat_id)

    try:
        response = await get_bot_files(chat_id, limit=10)
    except Exception:
        logger.exception("Failed to get files from DFSP")
        await message.answer(await get_message("files.fetch_error"))
        return

    if response is None:
        # 404 от API — чат не привязан
        from .start import get_main_keyboard

        keyboard = await get_main_keyboard(is_linked=False)
        await message.answer(await get_message("profile.not_linked"), reply_markup=keyboard)
        return

    if not response.files:
        from .start import get_main_keyboard

        keyboard = await get_main_keyboard(is_linked=True)
        await message.answer(await get_message("files.empty_with_menu"), reply_markup=keyboard)
        return

    header = await get_message("files.list_header")
    item_template = await get_message("files.list_item")
    empty_text = await get_message("files.list_empty")
    text = format_file_list(response.files, header, item_template, empty_text)
    keyboard = await build_files_keyboard(response.files, cursor=response.cursor, prev_cursor=None)

    # Добавляем кнопку "Главное меню" если её нет
    if keyboard and keyboard.inline_keyboard:
        # Проверяем есть ли уже кнопка "Главное меню"
        has_home = any(any(btn.callback_data == "menu:home" for btn in row) for row in keyboard.inline_keyboard)
        if not has_home:
            keyboard.inline_keyboard.append(
                [
                    InlineKeyboardButton(text=await get_message("buttons.home"), callback_data="menu:home"),
                ]
            )

    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data.startswith(CALLBACK_PREFIX))
async def handle_files_callback(callback: CallbackQuery) -> None:
    """Обработчик всех callback'ов для файлов."""
    if not callback.data:
        return  # Не наш callback, пропускаем

    data = callback.data
    if not data.startswith(CALLBACK_PREFIX):
        return

    signed_data = data[len(CALLBACK_PREFIX) :]

    # Подпись + TTL
    payload = verify(
        signed_data,
        CALLBACK_SECRET,
        ttl_seconds=CALLBACK_TTL,
        signature_bytes=CALLBACK_SIG_BYTES,
    )
    if payload is None:
        return  # Не наш callback или подпись/TTL невалидны

    token = payload.get("t")
    cmd_code = payload.get("c")
    cached = _get_payload(str(token)) if token else None
    if not cached:
        await callback.answer(await get_message("files.link_expired"), show_alert=True)
        return

    cmd = cached.get("cmd")
    if not cmd:
        cmd = {"o": "open", "v": "verify", "p": "page"}.get(cmd_code, cmd_code)
    # Проверяем, что это команда для файлов
    if cmd not in ("page", "open", "verify"):
        return  # Не наша команда, пропускаем
    chat_id = callback.message.chat.id if callback.message else None

    if not chat_id:
        await callback.answer(await get_message("common.no_chat"), show_alert=True)
        return

    if cmd == "page":
        # Пагинация
        cursor = cached.get("cursor")
        if not cursor:
            await callback.answer(await get_message("files.missing_cursor"), show_alert=True)
            return

        try:
            response = await get_bot_files(chat_id, limit=10, cursor=cursor)
        except Exception:
            logger.exception("Failed to get files from DFSP (pagination)")
            await callback.answer(await get_message("files.pagination_error"), show_alert=True)
            return

        if response is None or not response.files:
            await callback.answer(await get_message("files.not_found"), show_alert=True)
            return

        header = await get_message("files.list_header")
        item_template = await get_message("files.list_item")
        empty_text = await get_message("files.list_empty")
        text = format_file_list(response.files, header, item_template, empty_text)
        # Для кнопки "Назад" используем текущий cursor как prev_cursor
        keyboard = await build_files_keyboard(
            response.files,
            cursor=response.cursor,
            prev_cursor=cursor,  # Текущий cursor становится prev для следующей страницы
        )

        if callback.message:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()

    elif cmd == "open":
        # Открыть файл
        file_id = cached.get("file_id")
        if not file_id:
            await callback.answer(await get_message("files.missing_file_id"), show_alert=True)
            return

        # Убеждаемся, что id в hex с префиксом 0x
        if not file_id.startswith("0x"):
            file_id = f"0x{file_id}"

        # Формируем URL для открытия файла
        origin = str(settings.PUBLIC_WEB_ORIGIN).rstrip("/")
        file_url = f"{origin}/files/{file_id}"

        await callback.answer(await get_message("files.opening", variables={"file_prefix": file_id[:8]}))
        if callback.message:
            await callback.message.answer(
                await get_message("files.open_link", variables={"file_url": file_url}),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=await get_message("buttons.open_in_browser"),
                                url=file_url,
                            )
                        ]
                    ]
                ),
            )

    elif cmd == "verify":
        # Verify файла
        file_id = cached.get("file_id")
        if not file_id:
            await callback.answer(await get_message("files.missing_file_id"), show_alert=True)
            return

        # API ожидает формат 0x + 64 hex символа
        if not file_id.startswith("0x"):
            file_id = f"0x{file_id}"
        # Дополняем до 64 hex символов (32 байта)
        if len(file_id) < 66:  # 0x + 64 символа
            file_id = f"0x{file_id[2:].zfill(64)}"

        # Вызываем API для верификации
        try:
            api_url = str(settings.DFSP_API_URL).rstrip("/")
            url = f"{api_url}/bot/verify/{file_id}"
            headers = {"X-TG-Chat-Id": str(chat_id)}
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)

            if resp.status_code == 404:
                await callback.answer(await get_message("files.verify_not_found"), show_alert=True)
                return

            if resp.status_code == 400:
                await callback.answer(await get_message("verify.invalid_format_response"), show_alert=True)
                return

            resp.raise_for_status()
            data = resp.json()

            onchain_ok = data.get("onchain_ok", False)
            offchain_ok = data.get("offchain_ok", False)
            match = data.get("match", False)
            last_anchor_tx = data.get("lastAnchorTx")

            status_icon = "✅" if match else "❌"
            status_text = await get_message(
                "verify.status_match" if match else "verify.status_mismatch"
            )

            text = await get_message(
                "verify.summary",
                variables={
                    "status_icon": status_icon,
                    "onchain_icon": "✅" if onchain_ok else "❌",
                    "offchain_icon": "✅" if offchain_ok else "❌",
                    "status_text": status_text,
                },
            )

            if last_anchor_tx:
                text += await get_message(
                    "verify.summary_last_anchor",
                    variables={"tx": last_anchor_tx[:20]},
                )

            await callback.answer()
            if callback.message:
                await callback.message.answer(text, parse_mode="Markdown")

        except Exception:
            logger.exception("Failed to verify file")
            await callback.answer(await get_message("files.verify_failed"), show_alert=True)

    else:
        await callback.answer(await get_message("files.unknown_command"), show_alert=True)
