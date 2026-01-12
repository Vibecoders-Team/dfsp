# backend/tests/integration/conftest.py
import hashlib
import os
import secrets
import time
from collections.abc import Callable

import httpx
import pytest
from dotenv import load_dotenv

# Import our signer class from the root of the tests folder
# Pytest automatically adds the tests root to the path
from ..signer import EIP712Signer

# Load environment variables (e.g., from .env in the project root)
load_dotenv()

# --- Constants ---
DEV_CHAIN_ID = 31337

# --- Base fixtures ---


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Returns the base API URL from .env or uses a default."""
    return os.getenv("API_BASE", "http://localhost:8000")


@pytest.fixture(scope="session")
def ipfs_gateway_url() -> str:
    """Returns the IPFS gateway URL for E2E tests."""
    return os.getenv("IPFS_GATEWAY_HOST_PORT", "http://localhost:8080")


@pytest.fixture(scope="session")
def client(api_base_url: str) -> httpx.Client:
    """Main HTTP client for tests."""
    with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def wait_for_api(client: httpx.Client):
    """
    Automatically runs at the start of the session and waits for the API to become available.
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
    """Generates a random 32-byte ID in 0x... format."""
    return "0x" + secrets.token_hex(32)


# --- Authentication fixtures ---


@pytest.fixture(scope="session")
def test_signer() -> EIP712Signer:
    """
    Creates a one-time Ethereum account and returns a signer wrapper.
    Used in all tests that require a signature.
    """
    private_key = "0x" + secrets.token_hex(32)
    return EIP712Signer(private_key)


@pytest.fixture
def auth_headers(client: httpx.Client, test_signer: EIP712Signer) -> dict:
    """
    Performs a full registration/login cycle and returns headers
    with a valid access token for authorized requests.
    """
    # 1. Get challenge
    response = client.post("/auth/challenge", json={})
    assert response.status_code == 200, "Failed to get challenge"
    challenge_data = response.json()
    nonce = challenge_data["nonce"]

    # 2. Sign
    signature, typed_data = test_signer.sign(nonce)

    # 3. Prepare payload
    payload = {
        "eth_address": test_signer.address,
        "challenge_id": challenge_data["challenge_id"],
        "signature": signature,
        "typed_data": typed_data,
        "display_name": f"Pytest User {secrets.token_hex(4)}",
        "rsa_public": "test_rsa_key",
    }

    # 4. Try to log in. If it fails, register.
    # This makes the fixture resilient to repeated runs.
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


# --- Helpers ---


def wait_until_ok(
    request_func: Callable[[], httpx.Response],
    predicate: Callable[[httpx.Response], bool],
    timeout: int = 60,
    interval: int = 1,
    description: str = "Service is not ready",
):
    """Waits until the service is available and meets the condition."""
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
    Checks if a string is a 32-byte hex string with a 0x prefix.
    """
    if not isinstance(s, str) or not s.startswith("0x"):
        return False
    # 0x + 32 bytes * 2 chars/byte = 66 characters
    return len(s) == 66 and all(c in "0123456789abcdefABCDEF" for c in s[2:])


def _solve_pow(challenge: str, difficulty: int) -> str:
    """Solves a PoW challenge and returns the nonce as a string."""
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
    Fixture that returns a FACTORY (function) for generating PoW headers.
    This factory can be called multiple times within a single test.
    """

    def _generate() -> dict:
        # 1. Get challenge
        r = client.post("/pow/challenge")
        assert r.status_code == 200, "Failed to get PoW challenge"
        challenge_data = r.json()
        challenge = challenge_data["challenge"]
        difficulty = challenge_data["difficulty"]

        # 2. Solve it
        nonce = _solve_pow(challenge, difficulty)

        # 3. Return the ready header
        return {"X-PoW-Token": f"{challenge}.{nonce}"}

    return _generate
