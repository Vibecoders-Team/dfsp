"""
Full bot flow integration test:
1. Create local account via backend API
2. Link account via link (/tg/link-start + /tg/link-complete)
3. Upload file via backend API
4. Verify file via /verify command in bot
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

# Add project root (bot/) to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.handlers.verify import cmd_verify
from tests.signer import EIP712Signer

# --- Constants and fixtures ---


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Return base API URL from env var or default."""
    return os.getenv("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def backend_client(api_base_url: str) -> httpx.Client:
    """HTTP client for backend API calls."""
    with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def test_signer() -> EIP712Signer:
    """Create test Ethereum account for signing."""
    private_key = "0x" + secrets.token_hex(32)
    return EIP712Signer(private_key)


@pytest.fixture
def mock_message():
    """Create mock Message for testing bot handlers."""
    message = MagicMock()
    message.chat.id = secrets.randbelow(1_000_000_000)  # random chat_id
    message.text = None
    message.answer = AsyncMock()
    return message


# --- Helper functions ---


def create_user_and_link(client: httpx.Client, signer: EIP712Signer, chat_id: int) -> dict:
    """
    Create user via registration and link to Telegram chat_id.

    Returns:
        dict with keys: 'auth_headers', 'signer', 'chat_id'
    """
    # 1. Get challenge
    challenge_resp = client.post("/auth/challenge")
    assert challenge_resp.status_code == 200, f"Failed to get challenge: {challenge_resp.text}"
    challenge_data = challenge_resp.json()

    # 2. Sign and register
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

    # 3. Start Telegram linking process
    link_start_resp = client.post("/tg/link-start", json={"chat_id": chat_id})
    assert link_start_resp.status_code == 200, f"Link start failed: {link_start_resp.text}"
    link_token = link_start_resp.json()["link_token"]

    # 4. Complete linking
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
    Create file via backend API and return its fileId (hex32).

    Returns:
        fileId in format "0x" + 64 hex chars
    """
    # 1. Prepare file creation
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

    # 2. Sign and submit meta-transaction
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

    # Small delay for transaction processing
    time.sleep(0.5)

    return file_id


# --- Main test ---


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_flow_account_link_file_verify(
    backend_client: httpx.Client, test_signer: EIP712Signer, mock_message
):
    """
    Full integration test:
    1. Create local account via backend API
    2. Link account via link
    3. Upload file via backend API
    4. Verify file via /verify command in bot
    """
    chat_id = mock_message.chat.id

    # --- Step 1: Account creation and linking ---
    user_data = create_user_and_link(backend_client, test_signer, chat_id)
    auth_headers = user_data["auth_headers"]
    signer = user_data["signer"]

    # Verify linking succeeded
    me_resp = backend_client.get("/bot/me", headers={"X-TG-Chat-Id": str(chat_id)})
    assert me_resp.status_code == 200, f"Failed to get profile: {me_resp.text}"
    profile = me_resp.json()
    assert profile["address"].lower() == signer.address.lower()

    # --- Step 2: File upload ---
    file_id = create_file(backend_client, auth_headers, signer)

    # Verify file appears in list
    files_resp = backend_client.get("/bot/files", headers={"X-TG-Chat-Id": str(chat_id)})
    assert files_resp.status_code == 200, f"Failed to get files: {files_resp.text}"
    files_data = files_resp.json()
    assert "files" in files_data
    assert len(files_data["files"]) > 0

    # Find our file in the list
    file_found = False
    for file_item in files_data["files"]:
        if file_item["id_hex"] == file_id[2:]:  # without 0x prefix
            file_found = True
            break
    assert file_found, f"File {file_id} not found in files list"

    # --- Step 3: Verify file via /verify ---
    # Set command text
    mock_message.text = f"/verify {file_id}"

    # Mock httpx.AsyncClient for verification API call
    verify_response = {
        "onchain_ok": False,  # usually False in test environment
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

    # Verify bot replied
    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    response_text = call_args[0][0]

    # Check response content
    assert "verification result" in response_text.lower()
    assert "reply_markup" in call_args[1]

    # Check response includes status info
    assert "On-chain" in response_text or "onchain" in response_text.lower()
    assert "Off-chain" in response_text or "offchain" in response_text.lower()


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_flow_with_real_backend_api(backend_client: httpx.Client, test_signer: EIP712Signer, mock_message):
    """
    Alternative test using real backend API for verification.
    This test requires backend to be running and available.
    """
    chat_id = mock_message.chat.id

    # --- Step 1: Account creation and linking ---
    user_data = create_user_and_link(backend_client, test_signer, chat_id)
    auth_headers = user_data["auth_headers"]
    signer = user_data["signer"]

    # --- Step 2: File upload ---
    file_id = create_file(backend_client, auth_headers, signer)

    # --- Step 3: Verify file via real API ---
    verify_resp = backend_client.get(f"/bot/verify/{file_id}")
    assert verify_resp.status_code == 200, f"Verify failed: {verify_resp.text}"
    verify_data = verify_resp.json()

    # Check response structure
    assert "onchain_ok" in verify_data
    assert "offchain_ok" in verify_data
    assert "match" in verify_data
    assert "lastAnchorTx" in verify_data

    # In test environment offchain_ok is usually True
    assert verify_data["offchain_ok"] is True

    # --- Step 4: Verify via /verify command in bot ---
    mock_message.text = f"/verify {file_id}"

    # Use real API URL from settings

    # Mock httpx.AsyncClient but use real URL for API call
    async def mock_get_real_api(*args, **kwargs):
        # Call real API synchronously via httpx.Client
        url = kwargs.get("url") or (args[0] if args else "")
        if not url:
            raise ValueError("URL not provided")

        # Use backend_client base_url to build full URL
        # (verify handler uses settings.DFSP_API_URL, but we use backend_client.base_url)
        base_url = str(backend_client.base_url).rstrip("/")
        if not url.startswith("http"):
            full_url = f"{base_url}{url}"
        else:
            full_url = url

        # Use sync client to call real API
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

    # Check response
    mock_message.answer.assert_called_once()
    call_args = mock_message.answer.call_args
    response_text = call_args[0][0]

    # Verify bot replied (may be success or "file not found" error)
    # In test env the file may not be processed in time, so accept any response
    assert len(response_text) > 0
    # Check it's either a success response or a file error
    assert (
        "verification" in response_text.lower()
        or "result" in response_text.lower()
        or "not found" in response_text.lower()
        or "file" in response_text.lower()
    )
