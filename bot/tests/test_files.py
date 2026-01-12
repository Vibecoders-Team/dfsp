import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root (bot/) to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.handlers.files import cmd_files, handle_files_callback
from app.security.hmac import sign
from app.services.dfsp_api import BotFile, BotFileListResponse


@pytest.fixture
def mock_message():
    """Create a mock Message instance."""
    message = MagicMock()
    message.chat.id = 12345
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_callback():
    """Create a mock CallbackQuery instance."""
    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.chat.id = 12345
    callback.message.edit_text = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    callback.data = None
    return callback


@pytest.mark.asyncio
async def test_cmd_files_success(mock_message):
    """Test: /files command successfully returns file list."""
    files_response = BotFileListResponse(
        files=[
            BotFile(
                id_hex="1234567890abcdef",
                name="test.txt",
                size=1024,
                mime="text/plain",
                cid="QmTest",
                updatedAt="2024-01-01T00:00:00Z",
            )
        ],
        cursor="cursor123",
    )

    with patch("app.handlers.files.get_bot_files", return_value=files_response):
        await cmd_files(mock_message)

    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "test.txt" in call_args[0][0]
    assert call_args[1]["parse_mode"] == "Markdown"
    assert "reply_markup" in call_args[1]


@pytest.mark.asyncio
async def test_cmd_files_not_linked(mock_message):
    """Test: /files command for an unlinked chat."""
    with patch("app.handlers.files.get_bot_files", return_value=None):
        await cmd_files(mock_message)

    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "not linked" in call_args[0][0].lower()


@pytest.mark.asyncio
async def test_cmd_files_empty_list(mock_message):
    """Test: /files command for an empty file list."""
    files_response = BotFileListResponse(files=[], cursor=None)

    with patch("app.handlers.files.get_bot_files", return_value=files_response):
        await cmd_files(mock_message)

    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "no files" in call_args[0][0].lower()


@pytest.mark.asyncio
async def test_callback_page_success(mock_callback):
    """Test: pagination callback successfully updates the message."""
    cursor = "cursor123"
    payload = sign({"cmd": "page", "cursor": cursor}, settings.WEBHOOK_SECRET)
    mock_callback.data = payload

    files_response = BotFileListResponse(
        files=[
            BotFile(
                id_hex="abcdef",
                name="page2.txt",
                size=2048,
                mime="text/plain",
                cid="QmPage2",
                updatedAt="2024-01-02T00:00:00Z",
            )
        ],
        cursor="cursor456",
    )

    with patch("app.handlers.files.get_bot_files", return_value=files_response):
        await handle_files_callback(mock_callback)

    mock_callback.message.edit_text.assert_called_once()
    mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_callback_open_success(mock_callback):
    """Test: callback for opening a file."""
    file_id = "1234567890abcdef"
    payload = sign({"cmd": "open", "file_id": file_id}, settings.WEBHOOK_SECRET)
    mock_callback.data = payload

    await handle_files_callback(mock_callback)

    mock_callback.answer.assert_called_once()
    mock_callback.message.answer.assert_called_once()
    call_args = mock_callback.message.answer.call_args
    assert "open file" in call_args[0][0].lower()


@pytest.mark.asyncio
async def test_callback_verify_success(mock_callback):
    """Test: callback for file verification."""
    file_id = "1234567890abcdef"
    payload = sign({"cmd": "verify", "file_id": file_id}, settings.WEBHOOK_SECRET)
    mock_callback.data = payload

    verify_response = {
        "onchain_ok": True,
        "offchain_ok": True,
        "match": True,
        "lastAnchorTx": "0xabcdef",
    }

    # Mock httpx.AsyncClient
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = verify_response
    mock_resp.raise_for_status = MagicMock()

    async def mock_get(*args, **kwargs):
        return mock_resp

    mock_client_instance = AsyncMock()
    mock_client_instance.get = mock_get

    async def mock_aenter(self):
        return mock_client_instance

    async def mock_aexit(self, *args):
        return None

    mock_client_class = MagicMock()
    mock_client_class.return_value.__aenter__ = mock_aenter
    mock_client_class.return_value.__aexit__ = mock_aexit

    with patch("app.handlers.files.httpx.AsyncClient", mock_client_class):
        await handle_files_callback(mock_callback)

    mock_callback.answer.assert_called_once()
    mock_callback.message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_callback_invalid_signature(mock_callback):
    """Test: callback with invalid signature gets rejected."""
    mock_callback.data = "invalid.signature"

    await handle_files_callback(mock_callback)

    # Should NOT call answer, since this is not our callback
    mock_callback.answer.assert_not_called()


@pytest.mark.asyncio
async def test_callback_expired_signature(mock_callback):
    """Test: callback with expired signature gets rejected."""
    import time

    # Create a signature with an expired timestamp
    payload = sign(
        {"cmd": "page", "cursor": "test", "ts": int(time.time()) - 100},
        settings.WEBHOOK_SECRET,
        ttl_seconds=60,
    )
    mock_callback.data = payload

    await handle_files_callback(mock_callback)

    # Should not process expired callback
    mock_callback.answer.assert_not_called()


@pytest.mark.asyncio
async def test_callback_wrong_command(mock_callback):
    """Test: callback with unknown command is ignored."""
    payload = sign({"cmd": "unknown_command"}, settings.WEBHOOK_SECRET)
    mock_callback.data = payload

    await handle_files_callback(mock_callback)

    # Should not process unknown command
    mock_callback.answer.assert_not_called()
