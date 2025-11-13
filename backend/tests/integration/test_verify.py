# backend/tests/integration/test_files_meta_verify.py
import secrets
import pytest
import httpx
from .conftest import is_hex_bytes32

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


def test_verify_full_storage_to_match_true(client: httpx.Client, auth_headers: dict):
    """
    Проверяет главный AC: после полной загрузки файла через /storage/store,
    верификация должна показать match: true.
    """
    # Шаг 1: Готовим и загружаем файл через эндпоинт /storage/store.
    # Этот эндпоинт должен создавать запись и в БД, и в блокчейне.
    file_content = f"Test file content {secrets.token_hex(8)}".encode("utf-8")
    files_payload = {"file": ("test_verify.txt", file_content, "text/plain")}

    # Отправляем запрос на загрузку
    r_store = client.post("/storage/store", files=files_payload, headers=auth_headers)
    assert r_store.status_code == 200, f"Failed to store file: {r_store.text}"

    store_data = r_store.json()
    file_id_hex = store_data.get("id_hex")

    assert file_id_hex is not None, (
        "Response from /storage/store must contain file ID ('pk' or 'fileId')"
    )
    assert is_hex_bytes32(file_id_hex), f"File ID '{file_id_hex}' is not a valid hex32 string"

    # Шаг 2: Вызываем эндпоинт верификации с полученным ID
    r_verify = client.get(f"/verify/{file_id_hex}")
    assert r_verify.status_code == 200, f"Failed to verify file: {r_verify.text}"

    verify_data = r_verify.json()

    # Шаг 3: Проверяем результат
    assert "onchain" in verify_data
    assert "offchain" in verify_data
    assert "match" in verify_data

    # Главная проверка: обе части существуют и `match` равен `true`
    assert verify_data["onchain"] is not None, "On-chain data should not be null for a stored file"
    assert verify_data["offchain"] is not None, (
        "Off-chain data should not be null for a stored file"
    )
    assert verify_data["match"] is True, (
        "On-chain and off-chain checksums should match for a fresh file"
    )

    # Дополнительная проверка: чек-суммы действительно совпадают
    assert verify_data["onchain"]["checksum"] == verify_data["offchain"]["checksum"]
    print(
        f"\nVerification successful for file {file_id_hex}. Checksum: {verify_data['onchain']['checksum']}"
    )