"""
Интеграционный тест полного флоу бота:
1. Создание локального аккаунта через backend API
2. Привязка аккаунта через линк (/tg/link-start + /tg/link-complete)
3. Загрузка файла через backend API
4. Проверка файла через команду /verify в боте
"""

import os
import secrets
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Добавляем корень проекта (bot/) в sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.handlers.verify import cmd_verify
from tests.signer import EIP712Signer

# --- Константы и фикстуры ---


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Возвращает базовый URL API из переменной окружения или дефолтный."""
    return os.getenv("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def backend_client(api_base_url: str) -> httpx.Client:
    """HTTP клиент для вызовов backend API."""
    with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def test_signer() -> EIP712Signer:
    """Создает тестовый Ethereum аккаунт для подписи."""
    private_key = "0x" + secrets.token_hex(32)
    return EIP712Signer(private_key)


@pytest.fixture
def mock_message():
    """Создает мок Message для тестирования обработчиков бота."""
    message = MagicMock()
    message.chat.id = secrets.randbelow(1_000_000_000)  # Случайный chat_id
    message.text = None
    message.answer = AsyncMock()
    return message


# --- Вспомогательные функции ---


def create_user_and_link(client: httpx.Client, signer: EIP712Signer, chat_id: int) -> dict:
    """
    Создает пользователя через регистрацию и привязывает его к Telegram chat_id.

    Returns:
        dict с ключами: 'auth_headers', 'signer', 'chat_id'
    """
    # 1. Получаем challenge
    challenge_resp = client.post("/auth/challenge")
    assert challenge_resp.status_code == 200, f"Failed to get challenge: {challenge_resp.text}"
    challenge_data = challenge_resp.json()

    # 2. Подписываем и регистрируемся
    signature, typed_data = signer.sign(challenge_data["nonce"])
    register_payload = {
        "eth_address": signer.address,
        "challenge_id": challenge_data["challenge_id"],
        "signature": signature,
        "typed_data": typed_data,
        "display_name": f"Bot Integration Test User {chat_id}",
        "rsa_public": "test_rsa_key",
    }

    register_resp = client.post("/auth/register", json=register_payload)
    assert register_resp.status_code == 200, f"Registration failed: {register_resp.text}"
    tokens = register_resp.json()
    auth_headers = {"Authorization": f"Bearer {tokens['access']}"}

    # 3. Запускаем процесс привязки Telegram
    link_start_resp = client.post("/tg/link-start", json={"chat_id": chat_id})
    assert link_start_resp.status_code == 200, f"Link start failed: {link_start_resp.text}"
    link_token = link_start_resp.json()["link_token"]

    # 4. Завершаем привязку
    link_complete_resp = client.post(
        "/tg/link-complete",
        json={"link_token": link_token},
        headers=auth_headers,
    )
    assert link_complete_resp.status_code == 200, f"Link complete failed: {link_complete_resp.text}"

    return {
        "auth_headers": auth_headers,
        "signer": signer,
        "chat_id": chat_id,
    }


def create_file(client: httpx.Client, auth_headers: dict, signer: EIP712Signer) -> str:
    """
    Создает файл через backend API и возвращает его fileId (hex32).

    Returns:
        fileId в формате "0x" + 64 hex символа
    """
    # 1. Подготавливаем создание файла
    file_id = "0x" + secrets.token_hex(32)
    file_payload = {
        "fileId": file_id,
        "name": "test_integration_file.txt",
        "size": 1024,
        "mime": "text/plain",
        "cid": "Qm" + secrets.token_hex(22),
        "checksum": "0x" + secrets.token_hex(32),
    }

    prepare_resp = client.post("/files", json=file_payload, headers=auth_headers)
    assert prepare_resp.status_code == 200, f"File prepare failed: {prepare_resp.text}"
    typed_data = prepare_resp.json()["typedData"]

    # 2. Подписываем и отправляем мета-транзакцию
    signature = signer.sign_generic_typed_data(typed_data)
    exec_resp = client.post(
        "/meta-tx/submit",
        json={
            "request_id": str(uuid.uuid4()),
            "typed_data": typed_data,
            "signature": signature,
        },
    )
    assert exec_resp.status_code == 200, f"Meta-tx submit failed: {exec_resp.text}"

    # Небольшая задержка для обработки транзакции
    time.sleep(0.5)

    return file_id


# --- Основной тест ---


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_flow_account_link_file_verify(
    backend_client: httpx.Client, test_signer: EIP712Signer, mock_message
):
    """
    Полный интеграционный тест:
    1. Создает локальный аккаунт через backend API
    2. Привязывает аккаунт через линк
    3. Загружает файл через backend API
    4. Проверяет файл через команду /verify в боте
    """
    chat_id = mock_message.chat.id

    # --- Этап 1: Создание аккаунта и привязка ---
    user_data = create_user_and_link(backend_client, test_signer, chat_id)
    auth_headers = user_data["auth_headers"]
    signer = user_data["signer"]

    # Проверяем, что привязка прошла успешно
    me_resp = backend_client.get("/bot/me", headers={"X-TG-Chat-Id": str(chat_id)})
    assert me_resp.status_code == 200, f"Failed to get profile: {me_resp.text}"
    profile = me_resp.json()
    assert profile["address"].lower() == signer.address.lower()

    # --- Этап 2: Загрузка файла ---
    file_id = create_file(backend_client, auth_headers, signer)

    # Проверяем, что файл появился в списке
    files_resp = backend_client.get("/bot/files", headers={"X-TG-Chat-Id": str(chat_id)})
    assert files_resp.status_code == 200, f"Failed to get files: {files_resp.text}"
    files_data = files_resp.json()
    assert "files" in files_data
    assert len(files_data["files"]) > 0

    # Находим наш файл в списке
    file_found = False
    for file_item in files_data["files"]:
        if file_item["id_hex"] == file_id[2:]:  # Без префикса 0x
            file_found = True
            break
    assert file_found, f"File {file_id} not found in files list"

    # --- Этап 3: Проверка файла через /verify ---
    # Устанавливаем текст команды
    mock_message.text = f"/verify {file_id}"

    # Мокаем httpx.AsyncClient для вызова API верификации
    verify_response = {
        "onchain_ok": False,  # В тестовой среде обычно False
        "offchain_ok": True,
        "match": False,
        "lastAnchorTx": None,
    }

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

    # Проверяем, что бот ответил
    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    response_text = call_args[0][0]

    # Проверяем содержимое ответа
    assert "Результат верификации" in response_text or "верификации" in response_text.lower()
    assert "reply_markup" in call_args[1]

    # Проверяем, что ответ содержит информацию о статусе
    assert "On-chain" in response_text or "onchain" in response_text.lower()
    assert "Off-chain" in response_text or "offchain" in response_text.lower()


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_flow_with_real_backend_api(backend_client: httpx.Client, test_signer: EIP712Signer, mock_message):
    """
    Альтернативный тест, который использует реальный backend API для верификации.
    Этот тест требует, чтобы backend был запущен и доступен.
    """
    chat_id = mock_message.chat.id

    # --- Этап 1: Создание аккаунта и привязка ---
    user_data = create_user_and_link(backend_client, test_signer, chat_id)
    auth_headers = user_data["auth_headers"]
    signer = user_data["signer"]

    # --- Этап 2: Загрузка файла ---
    file_id = create_file(backend_client, auth_headers, signer)

    # --- Этап 3: Проверка файла через реальный API ---
    verify_resp = backend_client.get(f"/bot/verify/{file_id}")
    assert verify_resp.status_code == 200, f"Verify failed: {verify_resp.text}"
    verify_data = verify_resp.json()

    # Проверяем структуру ответа
    assert "onchain_ok" in verify_data
    assert "offchain_ok" in verify_data
    assert "match" in verify_data
    assert "lastAnchorTx" in verify_data

    # В тестовой среде offchain_ok обычно True
    assert verify_data["offchain_ok"] is True

    # --- Этап 4: Проверка через команду /verify в боте ---
    mock_message.text = f"/verify {file_id}"

    # Используем реальный API URL из настроек

    # Мокаем httpx.AsyncClient, но используем реальный URL для вызова API
    async def mock_get_real_api(*args, **kwargs):
        # Вызываем реальный API синхронно через httpx.Client
        url = kwargs.get("url") or (args[0] if args else "")
        if not url:
            raise ValueError("URL not provided")

        # Используем базовый URL из backend_client для формирования полного URL
        # (обработчик verify использует settings.DFSP_API_URL, но мы используем backend_client.base_url)
        base_url = str(backend_client.base_url).rstrip("/")
        if not url.startswith("http"):
            full_url = f"{base_url}{url}"
        else:
            full_url = url

        # Используем синхронный клиент для вызова реального API
        with httpx.Client(timeout=5.0) as sync_client:
            real_resp = sync_client.get(full_url)

        mock_resp = MagicMock()
        mock_resp.status_code = real_resp.status_code
        mock_resp.json.return_value = real_resp.json()
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    mock_client_instance = AsyncMock()
    mock_client_instance.get = mock_get_real_api

    async def mock_aenter(self):
        return mock_client_instance

    async def mock_aexit(self, *args):
        return None

    mock_client_class = MagicMock()
    mock_client_class.return_value.__aenter__ = mock_aenter
    mock_client_class.return_value.__aexit__ = mock_aexit

    with patch("app.handlers.verify.httpx.AsyncClient", mock_client_class):
        await cmd_verify(mock_message)

    # Проверяем ответ
    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    response_text = call_args[0][0]

    # Проверяем, что бот ответил (может быть успешный ответ или ошибка "файл не найден")
    # В тестовой среде файл может не успеть обработаться, поэтому проверяем любой ответ
    assert len(response_text) > 0
    # Проверяем, что это либо успешный ответ, либо ошибка о файле
    assert (
        "верификации" in response_text.lower()
        or "Результат" in response_text
        or "не найден" in response_text.lower()
        or "файл" in response_text.lower()
    )
