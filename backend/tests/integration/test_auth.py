# backend/tests/integration/test_auth.py
import pytest
import httpx
import secrets

from ..signer import EIP712Signer

pytestmark = pytest.mark.e2e


def test_challenge_ok(client: httpx.Client):
    response = client.post("/auth/challenge", json={})
    assert response.status_code == 200
    data = response.json()
    assert "challenge_id" in data
    assert "nonce" in data and data["nonce"].startswith("0x") and len(data["nonce"]) == 66
    assert "exp_sec" in data and data["exp_sec"] > 0


def test_register_and_login_via_eip712(client: httpx.Client, test_signer: EIP712Signer):
    # --- Шаг 1: Регистрация ---
    response = client.post("/auth/challenge", json={})
    assert response.status_code == 200
    challenge1 = response.json()

    signature1, typed_data1 = test_signer.sign(challenge1["nonce"])
    register_payload = {
        "eth_address": test_signer.address,
        "challenge_id": challenge1["challenge_id"],
        "signature": signature1,
        "typed_data": typed_data1,
        "display_name": "E2E Test User",
        "rsa_public": "test_rsa_key",
    }

    response = client.post("/auth/register", json=register_payload)
    assert response.status_code == 200, f"Registration failed: {response.text}"
    tokens = response.json()
    assert "access" in tokens and "refresh" in tokens

    # --- Шаг 2: Логин ---
    response = client.post("/auth/challenge", json={})
    assert response.status_code == 200
    challenge2 = response.json()

    signature2, typed_data2 = test_signer.sign(challenge2["nonce"])
    login_payload = {
        "eth_address": test_signer.address,
        "challenge_id": challenge2["challenge_id"],
        "signature": signature2,
        "typed_data": typed_data2,
    }

    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 200, f"Login failed: {response.text}"
    new_tokens = response.json()
    assert "access" in new_tokens and "refresh" in new_tokens


# --- Негативные кейсы ---


def test_register_typed_data_mismatch(client: httpx.Client, test_signer: EIP712Signer):
    response = client.post("/auth/challenge", json={})
    assert response.status_code == 200
    challenge = response.json()

    signature, typed_data = test_signer.sign(challenge["nonce"])
    typed_data["message"]["nonce"] = "0x" + "0" * 64

    payload = {
        "eth_address": test_signer.address,
        "challenge_id": challenge["challenge_id"],
        "signature": signature,
        "typed_data": typed_data,
        # ДОБАВЛЯЕМ НЕДОСТАЮЩИЕ ПОЛЯ
        "display_name": "Test Mismatch",
        "rsa_public": "test_rsa_key",
    }
    response = client.post("/auth/register", json=payload)

    assert response.status_code == 400
    assert "typed_data_mismatch" in response.json()["detail"]


def test_register_bad_signature(client: httpx.Client, test_signer: EIP712Signer):
    response = client.post("/auth/challenge", json={})
    assert response.status_code == 200
    challenge = response.json()

    _signature, typed_data = test_signer.sign(challenge["nonce"])
    bad_signature = "0x" + "1" * 130

    payload = {
        "eth_address": test_signer.address,
        "challenge_id": challenge["challenge_id"],
        "signature": bad_signature,
        "typed_data": typed_data,
        "display_name": "Test Bad Signature",
        "rsa_public": "test_rsa_key",
    }

    response = client.post("/auth/register", json=payload)
    assert response.status_code == 401
    assert "bad_signature" in response.json()["detail"]


def test_login_user_not_found(client: httpx.Client):
    # Создаем временный, незарегистрированный аккаунт
    unregistered_signer = EIP712Signer("0x" + secrets.token_hex(32))

    response = client.post("/auth/challenge", json={})
    assert response.status_code == 200
    challenge = response.json()

    signature, typed_data = unregistered_signer.sign(challenge["nonce"])
    payload = {
        "eth_address": unregistered_signer.address,
        "challenge_id": challenge["challenge_id"],
        "signature": signature,
        "typed_data": typed_data,
    }

    response = client.post("/auth/login", json=payload)
    # Сервер возвращает 401 с "user_not_found"
    assert response.status_code == 401
    assert "user_not_found" in response.json()["detail"]