from __future__ import annotations

import logging
import secrets
from collections.abc import Callable

import httpx
import pytest

pytestmark = pytest.mark.e2e

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
) -> tuple[str, str]:
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


def test_share_happy_and_duplicate(
    client: httpx.Client, auth_headers: dict, make_user, pow_header_factory: Callable[[], dict]
):
    grantee_addr, _ = make_user()
    file_id, _ = _create_file(client, auth_headers)
    req_id = "req-" + secrets.token_hex(8)
    body = {
        "users": [grantee_addr],
        "ttl_days": 7,
        "max_dl": 3,
        "encK_map": {grantee_addr: "c2VjcmV0LWtleQ=="},
        "request_id": req_id,
    }

    headers1 = {**auth_headers, **pow_header_factory()}
    r1 = client.post(f"/files/{file_id}/share", json=body, headers=headers1)
    assert r1.status_code == 200

    headers2 = {**auth_headers, **pow_header_factory()}
    r2 = client.post(f"/files/{file_id}/share", json=body, headers=headers2)
    assert r2.status_code == 200
    assert r2.json().get("status") == "duplicate"


def test_share_bad_file_id_400(
    client: httpx.Client, auth_headers: dict, pow_header_factory: Callable[[], dict]
):
    headers = {**auth_headers, **pow_header_factory()}
    # --- ИСПРАВЛЕНИЕ: Передаем минимально валидный JSON, чтобы избежать ошибки 422 ---
    addr = "0x" + ("11" * 20)
    body = {
        "users": [addr],
        "ttl_days": 1,
        "max_dl": 1,
        "encK_map": {addr: "a"},
        "request_id": "r1",
    }
    r = client.post("/files/0x1234/share", json=body, headers=headers)
    assert r.status_code == 400


def test_share_not_owner_403(
    client: httpx.Client, auth_headers: dict, make_user, pow_header_factory: Callable[[], dict]
):
    file_id, _ = _create_file(client, auth_headers)
    other_addr, other_headers = make_user()
    full_other_headers = {**other_headers, **pow_header_factory()}
    body = {
        "users": [other_addr],
        "ttl_days": 3,
        "max_dl": 1,
        "encK_map": {other_addr: "aw=="},
        "request_id": "req-" + secrets.token_hex(8),
    }
    r = client.post(f"/files/{file_id}/share", json=body, headers=full_other_headers)
    assert r.status_code == 403


def test_share_missing_encK_400(
    client: httpx.Client, auth_headers: dict, make_user, pow_header_factory: Callable[[], dict]
):
    grantee_addr, _ = make_user()
    file_id, _ = _create_file(client, auth_headers)
    headers = {**auth_headers, **pow_header_factory()}
    body = {
        "users": [grantee_addr],
        "ttl_days": 7,
        "max_dl": 3,
        "encK_map": {},
        "request_id": "req-" + secrets.token_hex(8),
    }
    r = client.post(f"/files/{file_id}/share", json=body, headers=headers)
    assert r.status_code == 400


def test_share_unknown_grantee_400(
    client: httpx.Client, auth_headers: dict, pow_header_factory: Callable[[], dict]
):
    file_id, _ = _create_file(client, auth_headers)
    unknown = "0x" + ("44" * 20)
    headers = {**auth_headers, **pow_header_factory()}
    body = {
        "users": [unknown],
        "ttl_days": 2,
        "max_dl": 1,
        "encK_map": {unknown: "aw=="},
        "request_id": "req-" + secrets.token_hex(8),
    }
    r = client.post(f"/files/{file_id}/share", json=body, headers=headers)
    assert r.status_code == 400


def test_share_requires_pow(
    client: httpx.Client, auth_headers: dict, make_user, pow_header_factory: Callable[[], dict]
):
    grantee_addr, _ = make_user()
    file_id, _ = _create_file(client, auth_headers)
    body = {
        "users": [grantee_addr],
        "ttl_days": 1,
        "max_dl": 1,
        "encK_map": {grantee_addr: "test"},
        "request_id": "pow-test-1",
    }

    r1 = client.post(f"/files/{file_id}/share", json=body, headers=auth_headers)
    assert r1.status_code == 429
    assert "pow_token_required" in r1.text

    headers = {**auth_headers, **pow_header_factory()}
    r2 = client.post(f"/files/{file_id}/share", json=body, headers=headers)
    assert r2.status_code == 200


@pytest.mark.slow
def test_share_meta_tx_quota(
    client: httpx.Client, auth_headers: dict, make_user, pow_header_factory: Callable[[], dict]
):
    grantee_addr, _ = make_user()
    file_id, _ = _create_file(client, auth_headers)

    # --- ИСПРАВЛЕНИЕ: Проверяем, что ошибка НАСТУПИТ в пределах разумного числа запросов ---
    # Мы делаем на 10 запросов больше лимита, чтобы гарантированно его превысить
    # даже если другие тесты потратили часть квоты.
    QUOTA_LIMIT = 50
    requests_to_make = QUOTA_LIMIT + 10

    quota_exceeded = False
    for i in range(requests_to_make):
        headers = {**auth_headers, **pow_header_factory()}
        body = {
            "users": [grantee_addr],
            "ttl_days": 1,
            "max_dl": 1,
            "encK_map": {grantee_addr: "test"},
            "request_id": f"quota-test-{i}",
        }
        r = client.post(f"/files/{file_id}/share", json=body, headers=headers)

        if r.status_code == 429:
            assert "meta_tx_quota_exceeded" in r.text
            quota_exceeded = True
            logger.info("Quota exceeded on request #%d, which is expected.", i + 1)
            break  # Выходим из цикла, как только получили нужную ошибку

    # Финальная проверка: убеждаемся, что мы действительно поймали ошибку превышения квоты
    assert quota_exceeded, f"Quota was not exceeded after {requests_to_make} requests"
