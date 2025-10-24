import secrets
import pytest
import httpx

from typing import Optional, Tuple
from web3 import Web3

from .conftest import is_hex_bytes32

pytestmark = pytest.mark.e2e


def _hex32() -> str:
    return "0x" + secrets.token_hex(32)


def _fake_cid() -> str:
    return "bafy" + secrets.token_hex(16)


def _create_file(client: httpx.Client, headers: dict, *, file_id: Optional[str] = None, checksum: Optional[str] = None) -> Tuple[str, str]:
    """Create a file record owned by the user behind headers. Returns (fileId, checksum)."""
    fid = file_id or _hex32()
    chk = checksum or _hex32()
    payload = {
        "fileId": fid,
        "name": f"file-{secrets.token_hex(4)}.bin",
        "size": 1234,
        "mime": "application/octet-stream",
        "cid": _fake_cid(),
        "checksum": chk,
    }
    r = client.post("/files", json=payload, headers=headers)
    assert r.status_code == 200, f"/files create failed: {r.status_code} {r.text}"
    return fid, chk


def test_share_happy_and_duplicate(client: httpx.Client, auth_headers: dict, make_user):
    """
    POST /files/{id}/share: happy path returns queued items and typedDataList;
    duplicate by request_id returns status=duplicate with same capIds.
    """
    # arrange: grantee exists in DB
    grantee_addr, _ = make_user()

    # arrange: create file as current user (auth_headers)
    file_id, _ = _create_file(client, auth_headers)

    # body
    req_id = "req-" + secrets.token_hex(8)
    enc_key_b64 = "c2VjcmV0LWtleQ=="  # base64("secret-key")
    body = {
        "users": [grantee_addr],
        "ttl_days": 7,
        "max_dl": 3,
        "encK_map": {grantee_addr: enc_key_b64},
        "request_id": req_id,
    }

    # act: first share
    r1 = client.post(f"/files/{file_id}/share", json=body, headers=auth_headers)
    assert r1.status_code == 200, f"unexpected {r1.status_code}: {r1.text}"
    j1 = r1.json()

    # assert: items
    assert isinstance(j1.get("items"), list) and len(j1["items"]) == 1
    item = j1["items"][0]
    assert item["grantee"].lower() == grantee_addr.lower()
    assert item["status"] == "queued"
    assert is_hex_bytes32(item["capId"])  # deterministic bytes32

    # assert: typedDataList present and valid-ish
    tdl = j1.get("typedDataList")
    assert isinstance(tdl, list) and len(tdl) == 1
    td = next(iter(tdl))
    assert td.get("primaryType") == "ForwardRequest"
    assert isinstance(td.get("domain"), dict)
    assert isinstance(td.get("types"), dict)
    assert isinstance(td.get("message"), dict)
    assert Web3.is_address(td["message"].get("from", ""))
    assert Web3.is_address(td["message"].get("to", ""))

    # duplicate with the same request_id
    r2 = client.post(f"/files/{file_id}/share", json=body, headers=auth_headers)
    assert r2.status_code == 200, f"duplicate should return 200, got {r2.status_code}: {r2.text}"
    j2 = r2.json()
    assert j2.get("status") == "duplicate"
    assert isinstance(j2.get("capIds"), list) and len(j2["capIds"]) == 1
    assert is_hex_bytes32(j2["capIds"][0])

    # invoke with a new request_id and ensure capIds are the same (nonce unchanged until meta-tx mined)
    body2 = dict(body)
    body2["request_id"] = "req-" + secrets.token_hex(8)
    r3 = client.post(f"/files/{file_id}/share", json=body2, headers=auth_headers)
    assert r3.status_code == 200, r3.text
    j3 = r3.json()
    assert j3["items"][0]["capId"].lower() == item["capId"].lower()


def test_share_bad_file_id_400(client: httpx.Client, auth_headers: dict):
    bad_id = "0x1234"
    addr = "0x" + ("11" * 20)
    body = {
        "users": [addr],
        "ttl_days": 7,
        "max_dl": 3,
        "encK_map": {addr: "eA=="},  # base64("x")
        "request_id": "req-" + secrets.token_hex(8),
    }
    r = client.post(f"/files/{bad_id}/share", json=body, headers=auth_headers)
    assert r.status_code == 400
    assert "bad_file_id" in r.text


def test_share_not_owner_403(client: httpx.Client, auth_headers: dict, make_user):
    # owner (user A) creates a file
    file_id, _ = _create_file(client, auth_headers)

    # create another user B to act as caller (not owner)
    other_addr, other_headers = make_user()

    # choose a valid grantee (user B), with encK
    body = {
        "users": [other_addr],  # any existing user; encK must be present
        "ttl_days": 3,
        "max_dl": 1,
        "encK_map": {other_addr: "aw=="},  # base64("k")
        "request_id": "req-" + secrets.token_hex(8),
    }

    r = client.post(f"/files/{file_id}/share", json=body, headers=other_headers)
    assert r.status_code == 403, f"expected 403 not_owner, got {r.status_code}: {r.text}"
    assert "not_owner" in r.text


def test_share_missing_encK_400(client: httpx.Client, auth_headers: dict, make_user):
    # arrange: grantee exists and file exists
    grantee_addr, _ = make_user()
    file_id, _ = _create_file(client, auth_headers)

    body = {
        "users": [grantee_addr],
        "ttl_days": 7,
        "max_dl": 3,
        "encK_map": {},  # missing key for grantee
        "request_id": "req-" + secrets.token_hex(8),
    }
    r = client.post(f"/files/{file_id}/share", json=body, headers=auth_headers)
    assert r.status_code == 400
    assert "encK_missing_for" in r.text


def test_share_unknown_grantee_400(client: httpx.Client, auth_headers: dict):
    file_id, _ = _create_file(client, auth_headers)
    unknown = "0x" + ("44" * 20)
    body = {
        "users": [unknown],
        "ttl_days": 2,
        "max_dl": 1,
        "encK_map": {unknown: "aw=="},  # base64("k")
        "request_id": "req-" + secrets.token_hex(8),
    }
    r = client.post(f"/files/{file_id}/share", json=body, headers=auth_headers)
    assert r.status_code == 400
    assert "unknown_grantee" in r.text
