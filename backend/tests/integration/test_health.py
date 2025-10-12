# backend/tests/integration/test_health.py
import pytest
import httpx

# Предполагаем, что DEV_CHAIN_ID будет импортирован из conftest
# Если нет, можно определить его здесь: DEV_CHAIN_ID = 31337
from .conftest import DEV_CHAIN_ID

# Маркируем все тесты в этом файле как 'e2e',
# так как они требуют запущенной инфраструктуры
pytestmark = pytest.mark.e2e


def test_health_ok_minimal(client: httpx.Client):
    """
    Проверяет базовую работоспособность API через реальный HTTP-запрос.
    GET /api/healthz → 200, api.ok is True
    """
    # ОБРАТИТЕ ВНИМАНИЕ: httpx.Client уже настроен на base_url,
    # поэтому мы указываем относительный путь
    response = client.get("/health")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text}"
    )

    data = response.json()
    # Адаптируем под вашу структуру ответа /healthz
    # Предполагаем, что полный ответ содержит ключ "api"
    assert data.get("api", {}).get("ok") is True, "API status should be 'ok: True'"


def test_health_dependencies(client: httpx.Client):
    """
    Проверяет состояние всех зависимостей через реальный HTTP-запрос.
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    # Проверяем базу данных
    assert data.get("db", {}).get("ok") is True, "Database connection should be OK"

    # Проверяем Redis
    assert data.get("redis", {}).get("ok") is True, "Redis connection should be OK"

    # Проверяем подключение к блокчейну
    chain_info = data.get("chain", {})
    assert chain_info.get("ok") is True, "Blockchain connection should be OK"
    assert chain_info.get("chainId") == DEV_CHAIN_ID, (
        f"Expected chainId {DEV_CHAIN_ID}, got {chain_info.get('chainId')}"
    )

    # Проверяем загруженные контракты
    contracts_info = data.get("contracts", {})
    assert contracts_info.get("ok") is True, "Contracts should be loaded correctly"
    assert isinstance(contracts_info.get("names"), list), "'contracts.names' should be a list"
    assert len(contracts_info.get("names", [])) >= 1, "At least one contract should be loaded"

    # Проверяем IPFS
    ipfs_info = data.get("ipfs", {})
    assert ipfs_info.get("ok") is True, "IPFS connection should be OK in dev environment"