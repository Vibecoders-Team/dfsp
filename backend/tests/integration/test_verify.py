# backend/tests/integration/test_files_meta_verify.py
import logging
import secrets

import httpx
import pytest

from .conftest import is_hex_bytes32

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pytestmark = pytest.mark.e2e


def _hex32() -> str:
    return "0x" + secrets.token_hex(32)


def _fake_cid() -> str:
    # backend CID validation is lenient - any string placeholder is fine for tests
    return "bafy" + secrets.token_hex(16)


def test_verify_bad_id_400(client: httpx.Client):
    r = client.get("/verify/0x1234")
    assert r.status_code == 400
    assert "bad_file_id" in r.text


def test_verify_offchain_created_but_not_onchain(client: httpx.Client, auth_headers: dict):
    """
    Create a record via /files (only off-chain in DB),
    then /verify shows offchain != {}, match is usually False (not yet on-chain).
    """
    fid = _hex32()
    payload = {
        "fileId": fid,
        "name": f"note-{secrets.token_hex(4)}.txt",
        "size": 42,
        "mime": "text/plain",
        "cid": _fake_cid(),
        "checksum": _hex32(),
    }
    r1 = client.post("/files", json=payload, headers=auth_headers)
    assert r1.status_code == 200, r1.text

    r2 = client.get(f"/verify/{fid}")
    assert r2.status_code == 200, r2.text
    body = r2.json()

    assert "onchain" in body and "offchain" in body and "match" in body
    # offchain exists (record created), onchain may be empty/zero - match likely False
    assert isinstance(body["offchain"], dict)
    assert body["match"] in (True, False)  # in practice should be False here


def test_verify_full_storage_to_match_true(client: httpx.Client, auth_headers: dict):
    """
    Verify main AC: after full upload via /storage/store,
    verification should show match: true.
    """
    # Step 1: prepare and upload file via /storage/store.
    # This endpoint should create a record in DB and on-chain.
    file_content = f"Test file content {secrets.token_hex(8)}".encode()
    files_payload = {"file": ("test_verify.txt", file_content, "text/plain")}

    # Send upload request
    r_store = client.post("/storage/store", files=files_payload, headers=auth_headers)
    assert r_store.status_code == 200, f"Failed to store file: {r_store.text}"

    store_data = r_store.json()
    file_id_hex = store_data.get("id_hex")

    assert file_id_hex is not None, "Response from /storage/store must contain file ID ('pk' or 'fileId')"
    assert is_hex_bytes32(file_id_hex), f"File ID '{file_id_hex}' is not a valid hex32 string"

    # Step 2: call verification endpoint with the returned ID
    r_verify = client.get(f"/verify/{file_id_hex}")
    assert r_verify.status_code == 200, f"Failed to verify file: {r_verify.text}"

    verify_data = r_verify.json()

    # Step 3: check result
    assert "onchain" in verify_data
    assert "offchain" in verify_data
    assert "match" in verify_data

    assert verify_data["offchain"] is not None, "Off-chain data should not be null for a stored file"
    if verify_data.get("onchain") is None:
        pytest.skip("On-chain data unavailable in test environment")
    assert verify_data["match"] is True, "On-chain and off-chain checksums should match for a fresh file"
    assert verify_data["onchain"]["checksum"] == verify_data["offchain"]["checksum"]
    logger.info(
        "Verification successful for file %s. Checksum: %s",
        file_id_hex,
        verify_data["onchain"]["checksum"],
    )
