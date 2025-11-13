import pytest
import httpx
import time
from ..signer import EIP712Signer

# Применяем маркер ко всем тестам в этом файле
pytestmark = pytest.mark.e2e

VALID_TEST_RSA_PUBLIC_KEY = "test_rsa_key"

def _register_and_get_token(client: httpx.Client, signer: EIP712Signer) -> str:
    """Вспомогательная функция для регистрации и получения access токена."""
    # Шаг 1: Получаем challenge
    response = client.post("/auth/challenge")
    assert response.status_code == 200
    challenge = response.json()

    # Шаг 2: Подписываем и регистрируемся
    signature, typed_data = signer.sign(challenge["nonce"])
    register_payload = {
        "eth_address": signer.address,
        "challenge_id": challenge["challenge_id"],
        "signature": signature,
        "typed_data": typed_data,
        "display_name": "TG Link Test User",
        "rsa_public": VALID_TEST_RSA_PUBLIC_KEY,
    }

    response = client.post("/auth/register", json=register_payload)
    assert response.status_code == 200, f"Registration failed: {response.text}"
    tokens = response.json()
    assert "access" in tokens
    return tokens["access"]


# --- Позитивные кейсы ---


def test_full_telegram_linking_flow(client: httpx.Client, test_signer: EIP712Signer):
    """
    Проверяет полный успешный сценарий:
    1. Регистрация для получения JWT.
    2. Вызов /tg/link-start для получения link_token.
    3. Вызов /tg/link-complete с JWT и link_token для завершения привязки.
    """
    # --- Этап 1: Аутентификация ---
    access_token = _register_and_get_token(client, test_signer)
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    # --- Этап 2: Запуск привязки (/link-start) ---
    chat_id = 123456789  # Тестовый chat_id
    response = client.post("/tg/link-start", json={"chat_id": chat_id})
    assert response.status_code == 200
    link_start_data = response.json()
    assert "link_token" in link_start_data
    assert "expires_at" in link_start_data
    link_token = link_start_data["link_token"]

    # --- Этап 3: Завершение привязки (/link-complete) ---
    response = client.post(
        "/tg/link-complete",
        json={"link_token": link_token},
        headers=auth_headers,  # Передаем JWT для аутентификации
    )
    assert response.status_code == 200, f"Link completion failed: {response.text}"
    assert response.json() == {"ok": True}

    # --- Этап 4 (Бонус): Проверяем, что токен одноразовый ---
    response = client.post(
        "/tg/link-complete", json={"link_token": link_token}, headers=auth_headers
    )
    assert response.status_code == 400
    assert "Invalid or expired link_token" in response.text


# --- Негативные кейсы ---


def test_link_complete_without_auth(client: httpx.Client):
    """Проверяет, что /link-complete требует аутентификации."""
    # Сначала получаем валидный link_token
    response = client.post("/tg/link-start", json={"chat_id": 987654321})
    assert response.status_code == 200
    link_token = response.json()["link_token"]

    # Теперь пытаемся его использовать БЕЗ заголовка Authorization
    response = client.post("/tg/link-complete", json={"link_token": link_token})
    assert response.status_code == 401  # Ожидаем 401 Unauthorized


@pytest.mark.parametrize('anyio_backend', ['asyncio'])
@pytest.mark.anyio
async def test_link_start_rate_limit(client: httpx.Client, anyio_backend):
    chat_id = 111222333
    limit = 5
    window = 60

    for _ in range(limit):
        response = client.post("/tg/link-start", json={"chat_id": chat_id})
        assert response.status_code == 200

    response = client.post("/tg/link-start", json={"chat_id": chat_id})
    assert response.status_code == 429
    assert "Too many requests" in response.text

    print(f"\nWaiting for {window + 2} seconds for rate limit window to pass...")
    time.sleep(window + 2)

    response = client.post("/tg/link-start", json={"chat_id": chat_id})
    assert response.status_code == 200
    print("Request after waiting was successful.")

    # Следующий запрос после ожидания должен снова пройти
    response = client.post("/tg/link-start", json={"chat_id": chat_id})
    assert response.status_code == 200
    print("Request after waiting was successful.")
    
def test_delete_link(client: httpx.Client, test_signer: EIP712Signer):
    """
    Проверяет флоу отзыва привязки:
    1. Создаем привязку.
    2. Отзываем ее через DELETE /tg/link.
    3. Проверяем идемпотентность, вызывая DELETE /tg/link еще раз.
    """
    # --- Этап 1: Создаем привязку, чтобы было что удалять ---
    access_token = _register_and_get_token(client, test_signer)
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    # Создаем link_token
    response = client.post("/tg/link-start", json={"chat_id": 444555666})
    assert response.status_code == 200
    link_token = response.json()["link_token"]

    # Завершаем привязку
    response = client.post(
        "/tg/link-complete", json={"link_token": link_token}, headers=auth_headers
    )
    assert response.status_code == 200, "Failed to create a link before testing deletion"

    # --- Этап 2: Отзываем привязку ---
    response = client.delete("/tg/link", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    # --- Этап 3: Проверяем идемпотентность ---
    # Повторный вызов не должен вызывать ошибку
    response = client.delete("/tg/link", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"ok": True}