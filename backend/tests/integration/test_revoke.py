import secrets
import pytest
import httpx
from typing import Optional, Tuple

from .conftest import is_hex_bytes32

pytestmark = pytest.mark.e2e


def _hex32() -> str:
    return "0x" + secrets.token_hex(32)


def _fake_cid() -> str:
    return "bafy" + secrets.token_hex(16)


def _create_file(client: httpx.Client, headers: dict, *, file_id: Optional[str] = None, checksum: Optional[str] = None) -> Tuple[str, str, str]:
    """Create a file record owned by the user behind headers. Returns (fileId, checksum, cid)."""
    fid = file_id or _hex32()
    chk = checksum or _hex32()
    cid = _fake_cid()
    payload = {
        "fileId": fid,
        "name": f"file-{secrets.token_hex(4)}.bin",
        "size": 1234,
        "mime": "application/octet-stream",
        "cid": cid,
        "checksum": chk,
    }
    r = client.post("/files", json=payload, headers=headers)
    assert r.status_code == 200, f"/files create failed: {r.status_code} {r.text}"
    return fid, chk, cid


def _share_one(client: httpx.Client, owner_headers: dict, file_id: str, grantee_addr: str, enc_b64: str) -> str:
    body = {
        "users": [grantee_addr],
        "ttl_days": 7,
        "max_dl": 3,
        "encK_map": {grantee_addr: enc_b64},
        "request_id": "req-" + secrets.token_hex(8),
    }
    r = client.post(f"/files/{file_id}/share", json=body, headers=owner_headers)
    assert r.status_code == 200, f"share failed: {r.status_code} {r.text}"
    j = r.json()
    assert isinstance(j.get("items"), list) and j["items"], j
    cap_id = j["items"][0]["capId"]
    assert is_hex_bytes32(cap_id)
    return cap_id


def test_revoke_happy_and_noop(client: httpx.Client, auth_headers: dict, make_user):
    # Arrange owner and grantee
    grantee_addr, _grantee_headers = make_user()
    file_id, _chk, _cid = _create_file(client, auth_headers)
    cap_id = _share_one(client, auth_headers, file_id, grantee_addr, "YQ==")

    # Act: revoke by grantor
    r1 = client.post(f"/grants/{cap_id}/revoke", headers=auth_headers)
    assert r1.status_code == 202, f"expected 202 queued, got {r1.status_code}: {r1.text}"
    j1 = r1.json()
    assert j1.get("status") == "queued"
    assert "task_id" in j1

    # Repeat revoke should be a noop (idempotent)
    r2 = client.post(f"/grants/{cap_id}/revoke", headers=auth_headers)
    assert r2.status_code == 200, f"expected 200 noop, got {r2.status_code}: {r2.text}"
    j2 = r2.json()
    assert j2.get("status") == "noop"


def test_revoke_not_grantor_403(client: httpx.Client, auth_headers: dict, make_user):
    grantee_addr, _ = make_user()
    file_id, _chk, _cid = _create_file(client, auth_headers)
    cap_id = _share_one(client, auth_headers, file_id, grantee_addr, "YQ==")

    # Another user tries to revoke
    other_addr, other_headers = make_user()
    r = client.post(f"/grants/{cap_id}/revoke", headers=other_headers)
    assert r.status_code == 403
    assert "not_grantor" in r.text


def test_revoke_bad_cap_id_400(client: httpx.Client, auth_headers: dict):
    r = client.post("/grants/0x1234/revoke", headers=auth_headers)
    assert r.status_code == 400
    assert "bad_cap_id" in r.text


def test_revoke_grant_not_found_404(client: httpx.Client, auth_headers: dict):
    cap_id = _hex32()
    r = client.post(f"/grants/{cap_id}/revoke", headers=auth_headers)
    assert r.status_code == 404
    assert "grant_not_found" in r.text

