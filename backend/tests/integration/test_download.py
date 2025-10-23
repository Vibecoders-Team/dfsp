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


def test_download_happy(client: httpx.Client, auth_headers: dict, make_user):
    # Arrange owner and grantee
    grantee_addr, grantee_headers = make_user()
    file_id, _chk, cid = _create_file(client, auth_headers)

    # Share to grantee
    enc_b64 = "c2VjcmV0LWtleQ=="  # base64("secret-key")
    cap_id = _share_one(client, auth_headers, file_id, grantee_addr, enc_b64)

    # Act: grantee requests download info
    r = client.get(f"/download/{cap_id}", headers=grantee_headers)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("encK") == enc_b64
    ipfs_path = j.get("ipfsPath", "")
    assert isinstance(ipfs_path, str) and ipfs_path.startswith("/ipfs/")


def test_download_not_grantee_403(client: httpx.Client, auth_headers: dict, make_user):
    # Owner and grantee
    grantee_addr, _grantee_headers = make_user()
    file_id, _chk, _cid = _create_file(client, auth_headers)
    cap_id = _share_one(client, auth_headers, file_id, grantee_addr, "YQ==")

    # Another user (not grantee) tries to download
    other_addr, other_headers = make_user()
    r = client.get(f"/download/{cap_id}", headers=other_headers)
    assert r.status_code == 403
    assert "not_grantee" in r.text


def test_download_bad_cap_id_400(client: httpx.Client, auth_headers: dict):
    r = client.get("/download/0x1234", headers=auth_headers)
    assert r.status_code == 400
    assert "bad_cap_id" in r.text


def test_download_grant_not_found_404(client: httpx.Client, auth_headers: dict):
    # random capId, but no such grant exists off-chain DB
    cap_id = _hex32()
    r = client.get(f"/download/{cap_id}", headers=auth_headers)
    assert r.status_code == 404
    assert "grant_not_found" in r.text

