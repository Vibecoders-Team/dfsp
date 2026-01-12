import httpx
import pytest

# Assume DEV_CHAIN_ID is imported from conftest
# If not, it can be defined here: DEV_CHAIN_ID = 31337
from .conftest import DEV_CHAIN_ID

# Mark all tests in this file as 'e2e',
# since they require running infrastructure
pytestmark = pytest.mark.e2e


def test_health_ok_minimal(client: httpx.Client):
    """
    Verify basic API health via real HTTP request.
    GET /api/healthz -> 200, api.ok is True
    """
    # NOTE: httpx.Client is already configured with base_url,
    # so we pass a relative path
    response = client.get("/health")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Body: {response.text}"

    data = response.json()
    assert data.get("status") in ("healthy", "degraded"), "API status should be 'healthy' or 'degraded'"


def test_health_dependencies(client: httpx.Client):
    """
    Verify status of all dependencies via real HTTP request.
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    checks = data.get("checks", {})

    # Check database
    assert checks.get("db") == "ok", "Database connection should be OK"

    # Check Redis
    assert checks.get("redis") == "ok", "Redis connection should be OK"

    # Check blockchain connection
    chain_info = checks.get("chain", {})
    assert chain_info.get("ok") is True, "Blockchain connection should be OK"
    assert chain_info.get("chainId") == DEV_CHAIN_ID, (
        f"Expected chainId {DEV_CHAIN_ID}, got {chain_info.get('chainId')}"
    )

    # Check loaded contracts
    contracts_info = checks.get("contracts", {})
    assert contracts_info.get("ok") is True, "Contracts should be loaded correctly"
    assert isinstance(contracts_info.get("names"), list), "'contracts.names' should be a list"
    assert len(contracts_info.get("names", [])) >= 1, "At least one contract should be loaded"

    # Check IPFS
    ipfs_info = checks.get("ipfs", {})
    assert ipfs_info.get("ok") is True, "IPFS connection should be OK in dev environment"
