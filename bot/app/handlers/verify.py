from __future__ import annotations

import logging
import re

import httpx
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import settings
from ..services.message_store import get_message

router = Router(name="verify")
logger = logging.getLogger(__name__)


def validate_file_id(file_id: str) -> str | None:
    """
    Validates fileId and brings it to the format 0x + 64 hex characters.

    Accepts:
    - With 0x prefix: "0x1234..." (must be 66 characters)
    - Without prefix: "1234..." (must be 64 hex characters)

    Returns:
        Normalized file_id in the format 0x + 64 hex or None if invalid
    """
    if not file_id:
        return None

    file_id = file_id.strip()

    # Check format with 0x
    if file_id.startswith("0x"):
        hex_part = file_id[2:]
        if len(file_id) == 66 and re.match(r"^[0-9a-fA-F]{64}$", hex_part):
            return file_id.lower()
        return None

    # Check format without 0x (64 hex characters)
    if re.match(r"^[0-9a-fA-F]{64}$", file_id):
        return f"0x{file_id.lower()}"

    return None


@router.message(Command("verify"))
async def cmd_verify(message: Message) -> None:
    """
    Handler for the /verify <fileId> command.

    Validation: hex32 (with or without 0x).
    Shows a short summary + a link to the full verification.
    """
    chat_id = message.chat.id
    logger.info("Handling /verify for chat_id=%s", chat_id)

    # Extract fileId from the command
    command_text = message.text or ""
    parts = command_text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(await get_message("verify.missing_id"), parse_mode="Markdown")
        return

    file_id_input = parts[1]
    file_id = validate_file_id(file_id_input)

    if not file_id:
        await message.answer(await get_message("verify.invalid_format"), parse_mode="Markdown")
        return

    # Call the API for verification
    try:
        api_url = str(settings.DFSP_API_URL).rstrip("/")
        url = f"{api_url}/bot/verify/{file_id}"
        headers = {"X-TG-Chat-Id": str(chat_id)}
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code == 404:
            await message.answer(
                await get_message("verify.not_found", variables={"file_id": file_id[:20]}),
                parse_mode="Markdown",
            )
            return

        if resp.status_code == 400:
            await message.answer(await get_message("verify.invalid_format_response"), parse_mode="Markdown")
            return

        resp.raise_for_status()
        data = resp.json()

        onchain_ok = data.get("onchain_ok", False)
        offchain_ok = data.get("offchain_ok", False)
        match = data.get("match", False)
        last_anchor_tx = data.get("lastAnchorTx")

        # Form a short summary
        status_icon = "✅" if match else "❌"
        status_text = await get_message("verify.status_match" if match else "verify.status_mismatch")

        summary = await get_message(
            "verify.summary",
            variables={
                "status_icon": status_icon,
                "onchain_icon": "✅" if onchain_ok else "❌",
                "offchain_icon": "✅" if offchain_ok else "❌",
                "status_text": status_text,
            },
        )

        if last_anchor_tx:
            summary += await get_message(
                "verify.summary_last_anchor",
                variables={"tx": last_anchor_tx[:20]},
            )

        # Build URL for full verification
        origin = str(settings.PUBLIC_WEB_ORIGIN).rstrip("/")
        full_verify_url = f"{origin}/verify/{file_id}"

        # Build "Open full verification" and "Main menu" buttons
        full_verify_btn = await get_message("buttons.verify_full")
        home_btn = await get_message("buttons.home")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=full_verify_btn, url=full_verify_url)],
                [InlineKeyboardButton(text=home_btn, callback_data="menu:home")],
            ]
        )

        await message.answer(summary, reply_markup=keyboard, parse_mode="Markdown")

    except httpx.HTTPStatusError as e:
        logger.exception("Failed to verify file: HTTP error")
        status_code = e.response.status_code if e.response else "unknown"
        await message.answer(
            await get_message("verify.http_error", variables={"status_code": status_code}),
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Failed to verify file")
        await message.answer(await get_message("verify.generic_error"), parse_mode="Markdown")
