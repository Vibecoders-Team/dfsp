import secrets
from collections.abc import Callable

import httpx
import pytest

from .conftest import is_hex_bytes32

pytestmark = pytest.mark.e2e


def _hex32() -> str:
    return "0x" + secrets.token_hex(32)


def _fake_cid() -> str:
    return "bafy" + secrets.token_hex(16)


def _create_file(
    client: httpx.Client,
    headers: dict,
    *,
    file_id: str | None = None,
    checksum: str | None = None,
) -> tuple[str, str, str]:
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


# --- ИЗМЕНЕНИЕ: Хелпер теперь принимает фабрику PoW ---
def _share_one(
    client: httpx.Client,
    owner_headers: dict,
    file_id: str,
    grantee_addr: str,
    enc_b64: str,
    pow_factory: Callable[[], dict],
) -> str:
    """Share a file. Returns capId."""
    body = {
        "users": [grantee_addr],
        "ttl_days": 7,
        "max_dl": 3,
        "encK_map": {grantee_addr: enc_b64},
        "request_id": "req-" + secrets.token_hex(8),
    }

    # Генерируем PoW и объединяем заголовки
    full_headers = {**owner_headers, **pow_factory()}

    r = client.post(f"/files/{file_id}/share", json=body, headers=full_headers)
    assert r.status_code == 200, f"share failed: {r.status_code} {r.text}"
    j = r.json()
    assert isinstance(j.get("items"), list) and j["items"], j
    cap_id = j["items"][0]["capId"]
    assert is_hex_bytes32(cap_id)
    return cap_id


# --- ИСПРАВЛЕННЫЕ ТЕСТЫ ---


def test_download_happy(
    client: httpx.Client, auth_headers: dict, make_user, pow_header_factory: Callable[[], dict]
):
    grantee_addr, grantee_headers = make_user()
    file_id, _chk, cid = _create_file(client, auth_headers)
    enc_b64 = "c2VjcmV0LWtleQ=="

    # Передаем фабрику в хелпер
    cap_id = _share_one(client, auth_headers, file_id, grantee_addr, enc_b64, pow_header_factory)

    # Act: grantee requests download info (требует свой PoW)
    full_grantee_headers = {**grantee_headers, **pow_header_factory()}
    r = client.get(f"/download/{cap_id}", headers=full_grantee_headers)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("encK") == enc_b64
    assert j.get("ipfsPath", "").startswith("/ipfs/")


def test_download_not_grantee_403(
    client: httpx.Client, auth_headers: dict, make_user, pow_header_factory: Callable[[], dict]
):
    grantee_addr, _grantee_headers = make_user()
    file_id, _chk, _cid = _create_file(client, auth_headers)
    cap_id = _share_one(client, auth_headers, file_id, grantee_addr, "YQ==", pow_header_factory)

    # Другой пользователь (не grantee) пытается скачать
    other_addr, other_headers = make_user()
    full_other_headers = {**other_headers, **pow_header_factory()}
    r = client.get(f"/download/{cap_id}", headers=full_other_headers)
    assert r.status_code == 403
    assert "not_grantee" in r.text


def test_download_bad_cap_id_400(
    client: httpx.Client, auth_headers: dict, pow_header_factory: Callable[[], dict]
):
    headers = {**auth_headers, **pow_header_factory()}
    r = client.get("/download/0x1234", headers=headers)
    assert r.status_code == 400
    assert "bad_cap_id" in r.text


def test_download_grant_not_found_404(
    client: httpx.Client, auth_headers: dict, pow_header_factory: Callable[[], dict]
):
    headers = {**auth_headers, **pow_header_factory()}
    cap_id = _hex32()
    r = client.get(f"/download/{cap_id}", headers=headers)
    assert r.status_code == 404
    assert "grant_not_found" in r.text
