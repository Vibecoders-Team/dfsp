import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Добавляем корень проекта (bot/) в sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.handlers.verify import cmd_verify, validate_file_id


@pytest.fixture
def mock_message():
    """Создает мок Message."""
    message = MagicMock()
    message.chat.id = 12345
    message.text = None
    message.answer = AsyncMock()
    return message


def test_validate_file_id_with_0x_prefix():
    """Тест: валидация fileId с префиксом 0x."""
    valid_id = "0x" + "a" * 64
    assert validate_file_id(valid_id) == valid_id.lower()

    invalid_short = "0x" + "a" * 63
    assert validate_file_id(invalid_short) is None

    invalid_long = "0x" + "a" * 65
    assert validate_file_id(invalid_long) is None

    invalid_chars = "0x" + "g" * 64
    assert validate_file_id(invalid_chars) is None


def test_validate_file_id_without_0x_prefix():
    """Тест: валидация fileId без префикса 0x."""
    valid_id = "a" * 64
    assert validate_file_id(valid_id) == f"0x{valid_id.lower()}"

    invalid_short = "a" * 63
    assert validate_file_id(invalid_short) is None

    invalid_long = "a" * 65
    assert validate_file_id(invalid_long) is None

    invalid_chars = "g" * 64
    assert validate_file_id(invalid_chars) is None


def test_validate_file_id_empty():
    """Тест: валидация пустого fileId."""
    assert validate_file_id("") is None
    assert validate_file_id(None) is None


@pytest.mark.asyncio
async def test_cmd_verify_success(mock_message):
    """Тест: команда /verify успешно обрабатывает валидный fileId."""
    file_id = "0x" + "a" * 64
    mock_message.text = f"/verify {file_id}"

    verify_response = {
        "onchain_ok": True,
        "offchain_ok": True,
        "match": True,
        "lastAnchorTx": "0xabcdef",
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = verify_response
        mock_resp.raise_for_status = MagicMock()

        async def mock_get(*args, **kwargs):
            return mock_resp

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get = mock_get
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_client_instance

        await cmd_verify(mock_message)

    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "Результат верификации" in call_args[0][0]
    assert "reply_markup" in call_args[1]


@pytest.mark.asyncio
async def test_cmd_verify_no_file_id(mock_message):
    """Тест: команда /verify без fileId показывает ошибку."""
    mock_message.text = "/verify"

    await cmd_verify(mock_message)

    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "Не указан ID файла" in call_args[0][0]  # noqa: RUF001


@pytest.mark.asyncio
async def test_cmd_verify_invalid_format(mock_message):
    """Тест: команда /verify с невалидным форматом показывает ошибку."""
    mock_message.text = "/verify invalid"

    await cmd_verify(mock_message)

    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "Неверный формат ID файла" in call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_verify_file_not_found(mock_message):
    """Тест: команда /verify для несуществующего файла."""
    file_id = "0x" + "a" * 64
    mock_message.text = f"/verify {file_id}"

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        async def mock_get(*args, **kwargs):
            return mock_resp

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value.get = mock_get
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_client_instance

        await cmd_verify(mock_message)

    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "не найден" in call_args[0][0].lower()


@pytest.mark.asyncio
async def test_cmd_verify_without_0x_prefix(mock_message):
    """Тест: команда /verify принимает fileId без префикса 0x."""
    file_id_no_prefix = "a" * 64
    mock_message.text = f"/verify {file_id_no_prefix}"

    verify_response = {
        "onchain_ok": True,
        "offchain_ok": True,
        "match": True,
        "lastAnchorTx": None,
    }

    # Мокаем httpx.AsyncClient
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

    with patch("app.handlers.verify.httpx.AsyncClient", mock_client_class):
        await cmd_verify(mock_message)

    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    assert "Результат верификации" in call_args[0][0]
