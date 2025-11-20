# backend/tests/integration/conftest.py
import hashlib
import os
import secrets
import time
from collections.abc import Callable

import httpx
import pytest
from dotenv import load_dotenv

# Импортируем наш класс-подписчик из корня папки tests
# Pytest автоматически добавляет корень tests в путь
from ..signer import EIP712Signer

# Загружаем переменные окружения (например, из .env в корне проекта)
load_dotenv()

# --- Константы ---
DEV_CHAIN_ID = 31337

# --- Базовые фикстуры ---


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Возвращает базовый URL API из .env или использует дефолтный."""
    return os.getenv("API_BASE", "http://localhost:8000")


@pytest.fixture(scope="session")
def ipfs_gateway_url() -> str:
    """Возвращает URL IPFS шлюза для E2E тестов."""
    return os.getenv("IPFS_GATEWAY_HOST_PORT", "http://localhost:8080")


@pytest.fixture(scope="session")
def client(api_base_url: str) -> httpx.Client:
    """Основной HTTP-клиент для тестов."""
    with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def wait_for_api(client: httpx.Client):
    """
    Автоматически запускается в начале сессии и ждет, пока API станет доступен.
    """
    ready_url = "/ready"

    def is_api_ready(response: httpx.Response) -> bool:
        return response.is_success

    wait_until_ok(
        lambda: client.get(ready_url),
        predicate=is_api_ready,
        timeout=60,
        interval=2,
        description=f"API is not ready at {client.base_url}{ready_url}",
    )


@pytest.fixture
def random_id_hex() -> str:
    """Генерирует случайный 32-байтный ID в формате 0x..."""
    return "0x" + secrets.token_hex(32)


# --- Фикстуры для аутентификации ---


@pytest.fixture(scope="session")
def test_signer() -> EIP712Signer:
    """
    Создает одноразовый Ethereum аккаунт и возвращает обертку-подписчик.
    Используется во всех тестах, где нужна подпись.
    """
    private_key = "0x" + secrets.token_hex(32)
    return EIP712Signer(private_key)


@pytest.fixture
def auth_headers(client: httpx.Client, test_signer: EIP712Signer) -> dict:
    """
    Выполняет полный цикл регистрации/логина и возвращает заголовки
    с валидным access-токеном для авторизованных запросов.
    """
    # 1. Получаем challenge
    response = client.post("/auth/challenge", json={})
    assert response.status_code == 200, "Failed to get challenge"
    challenge_data = response.json()
    nonce = challenge_data["nonce"]

    # 2. Подписываем
    signature, typed_data = test_signer.sign(nonce)

    # 3. Готовим payload
    payload = {
        "eth_address": test_signer.address,
        "challenge_id": challenge_data["challenge_id"],
        "signature": signature,
        "typed_data": typed_data,
        "display_name": f"Pytest User {secrets.token_hex(4)}",
        "rsa_public": "test_rsa_key",
    }

    # 4. Пробуем залогиниться. Если не получается - регистрируемся.
    # Это делает фикстуру устойчивой к повторным запускам.
    response = client.post("/auth/login", json=payload)
    if response.status_code == 401 and "user_not_found" in response.text:
        response = client.post("/auth/register", json=payload)

    assert response.status_code == 200, f"Failed to login/register. Body: {response.text}"

    tokens = response.json()
    access_token = tokens["access"]

    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def make_user(client: httpx.Client) -> Callable[[], tuple[str, dict]]:
    """Factory to register a fresh user and return (address, auth_headers)."""

    def _create() -> tuple[str, dict]:
        import secrets as _secrets

        signer = EIP712Signer("0x" + _secrets.token_hex(32))
        r1 = client.post("/auth/challenge", json={})
        assert r1.status_code == 200, r1.text
        ch = r1.json()
        sig, typed = signer.sign(ch["nonce"])  # EIP-712 login typed data
        payload = {
            "eth_address": signer.address,
            "challenge_id": ch["challenge_id"],
            "signature": sig,
            "typed_data": typed,
            "display_name": f"PyUser-{_secrets.token_hex(4)}",
            "rsa_public": "test_rsa_key",
        }
        r2 = client.post("/auth/register", json=payload)
        assert r2.status_code == 200, r2.text
        tokens = r2.json()
        return signer.address, {"Authorization": f"Bearer {tokens['access']}"}

    return _create


# --- Хелперы ---


def wait_until_ok(
    request_func: Callable[[], httpx.Response],
    predicate: Callable[[httpx.Response], bool],
    timeout: int = 60,
    interval: int = 1,
    description: str = "Service is not ready",
):
    """Ожидает, пока сервис не станет доступен и не удовлетворит условию."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = request_func()
            if predicate(response):
                return
        except httpx.RequestError:
            pass
        time.sleep(interval)
    pytest.fail(f"Timeout: {description}")


def is_hex_bytes32(s: str) -> bool:
    """
    Проверяет, является ли строка 32-байтной hex-строкой с префиксом 0x.
    """
    if not isinstance(s, str) or not s.startswith("0x"):
        return False
    # 0x + 32 байта * 2 символа/байт = 66 символов
    return len(s) == 66 and all(c in "0123456789abcdefABCDEF" for c in s[2:])


def _solve_pow(challenge: str, difficulty: int) -> str:
    """Решает PoW-задачу и возвращает nonce в виде строки."""
    prefix = "0" * ((difficulty + 3) // 4)
    nonce = 0
    while True:
        h = hashlib.sha256(f"{challenge}{nonce}".encode()).hexdigest()
        if h.startswith(prefix):
            return str(nonce)
        nonce += 1


@pytest.fixture
def pow_header_factory(client: httpx.Client) -> Callable[[], dict]:
    """
    Фикстура, которая возвращает ФАБРИКУ (функцию) для генерации PoW-заголовков.
    Эту фабрику можно вызывать много раз внутри одного теста.
    """

    def _generate() -> dict:
        # 1. Получаем челлендж
        r = client.post("/pow/challenge")
        assert r.status_code == 200, "Failed to get PoW challenge"
        challenge_data = r.json()
        challenge = challenge_data["challenge"]
        difficulty = challenge_data["difficulty"]

        # 2. Решаем его
        nonce = _solve_pow(challenge, difficulty)

        # 3. Возвращаем готовый заголовок
        return {"X-PoW-Token": f"{challenge}.{nonce}"}

    return _generate
