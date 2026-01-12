import time

import httpx
import pytest

from ..signer import EIP712Signer

# Apply marker to all tests in this file
pytestmark = pytest.mark.e2e

VALID_TEST_RSA_PUBLIC_KEY = "test_rsa_key"


def _register_and_get_token(client: httpx.Client, signer: EIP712Signer) -> str:
    """Helper to register and get access token."""
    # Step 1: get challenge
    response = client.post("/auth/challenge")
    assert response.status_code == 200
    challenge = response.json()

    # Step 2: sign and register
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


# --- Positive cases ---


def test_full_telegram_linking_flow(client: httpx.Client, test_signer: EIP712Signer):
    """
    Verify full success flow:
    1. Register to obtain JWT.
    2. Call /tg/link-start to get link_token.
    3. Call /tg/link-complete with JWT and link_token to finish linking.
    """
    # --- Step 1: Authentication ---
    access_token = _register_and_get_token(client, test_signer)
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    # --- Step 2: Start linking (/link-start) ---
    chat_id = 123456789  # test chat_id
    response = client.post("/tg/link-start", json={"chat_id": chat_id})
    assert response.status_code == 200
    link_start_data = response.json()
    assert "link_token" in link_start_data
    assert "expires_at" in link_start_data
    link_token = link_start_data["link_token"]

    # --- Step 3: Complete linking (/link-complete) ---
    response = client.post(
        "/tg/link-complete",
        json={"link_token": link_token},
        headers=auth_headers,  # pass JWT for auth
    )
    assert response.status_code == 200, f"Link completion failed: {response.text}"
    assert response.json() == {"ok": True}

    # --- Step 4 (Bonus): verify token is one-time ---
    response = client.post("/tg/link-complete", json={"link_token": link_token}, headers=auth_headers)
    assert response.status_code == 400
    assert "Invalid or expired link_token" in response.text


# --- Negative cases ---


def test_link_complete_without_auth(client: httpx.Client):
    """Verify that /link-complete requires authentication."""
    # First, get a valid link_token
    response = client.post("/tg/link-start", json={"chat_id": 987654321})
    assert response.status_code == 200
    link_token = response.json()["link_token"]

    # Now try to use it WITHOUT Authorization header
    response = client.post("/tg/link-complete", json={"link_token": link_token})
    assert response.status_code == 401  # expect 401 Unauthorized


@pytest.mark.parametrize("anyio_backend", ["asyncio"])
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

    time.sleep(window + 2)

    response = client.post("/tg/link-start", json={"chat_id": chat_id})
    assert response.status_code == 200

    # Next request after waiting should pass again
    response = client.post("/tg/link-start", json={"chat_id": chat_id})
    assert response.status_code == 200


def test_delete_link(client: httpx.Client, test_signer: EIP712Signer):
    """
    Verify unlink flow:
    1. Create a link.
    2. Revoke it via DELETE /tg/link.
    3. Check idempotency by calling DELETE /tg/link again.
    """
    # --- Step 1: Create a link so there is something to delete ---
    access_token = _register_and_get_token(client, test_signer)
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    # Create link_token
    response = client.post("/tg/link-start", json={"chat_id": 444555666})
    assert response.status_code == 200
    link_token = response.json()["link_token"]

    # Complete the link
    response = client.post("/tg/link-complete", json={"link_token": link_token}, headers=auth_headers)
    assert response.status_code == 200, "Failed to create a link before testing deletion"

    # --- Step 2: Revoke the link ---
    response = client.delete("/tg/link", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    # --- Step 3: Check idempotency ---
    # Repeat call should not error
    response = client.delete("/tg/link", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
