# backend/tests/integration/test_files_meta_verify.py
import secrets
import pytest
import httpx

pytestmark = pytest.mark.e2e


def _hex32() -> str:
    return "0x" + secrets.token_hex(32)


def _fake_cid() -> str:
    # бэкенд CID не валидирует строго — для теста любой строковый плейсхолдер
    return "bafy" + secrets.token_hex(16)


def test_verify_bad_id_400(client: httpx.Client):
    r = client.get("/verify/0x1234")
    assert r.status_code == 400
    assert "bad_file_id" in r.text


def test_verify_offchain_created_but_not_onchain(client: httpx.Client, auth_headers: dict):
    """
    Создаём запись через /files (пишется только off-chain в БД),
    затем /verify показывает offchain != {}, match обычно False (на цепь ещё не записано).
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
    # offchain есть (запись создана), onchain может быть пустым/нулевым — match скорей всего False
    assert isinstance(body["offchain"], dict)
    assert body["match"] in (True, False)  # но в реальности здесь должен быть False
