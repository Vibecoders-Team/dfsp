import pytest
import httpx
import hashlib

# Предполагаем, что conftest.py находится в той же папке
from .conftest import is_hex_bytes32

pytestmark = pytest.mark.e2e

# --- Тесты для /storage ---


def test_store_ok_then_cid_meta(client: httpx.Client, auth_headers: dict, test_signer):
    """
    5.1. Полный цикл: загрузка файла -> проверка cid -> проверка meta.
    """
    file_content = b"This is the content of my test file for DFSP."
    file_name = "test_readme.md"
    files = {"file": (file_name, file_content, "text/plain")}

    # 1. Загружаем файл
    response = client.post("/storage/store", files=files, headers=auth_headers)
    assert response.status_code == 200, f"Store failed: {response.text}"

    store_data = response.json()
    file_id = store_data.get("id_hex")
    assert file_id and is_hex_bytes32(file_id), "Response should contain a valid id_hex"

    # 2. Получаем CID по id_hex
    response = client.get(f"/storage/cid/{file_id}", headers=auth_headers)
    assert response.status_code == 200
    cid_data = response.json()
    assert cid_data.get("cid") == store_data.get("cid"), (
        "CID from /cid endpoint must match store response"
    )
    assert "url" in cid_data, "Response from /cid should contain a URL"

    # 3. Получаем метаданные по id_hex
    response = client.get(f"/storage/meta/{file_id}", headers=auth_headers)
    assert response.status_code == 200
    meta_data = response.json()

    assert meta_data.get("owner").lower() == test_signer.address.lower()
    assert is_hex_bytes32(meta_data.get("checksum"))
    assert meta_data.get("size") == len(file_content)
    assert meta_data.get("mime") == "text/plain"
    assert meta_data.get("createdAt") > 0


def test_store_with_custom_id_then_versions(
    client: httpx.Client, auth_headers: dict, random_id_hex: str
):
    """
    5.2. Загружаем две версии файла с одним id_hex и проверяем историю версий.
    """
    file_id = random_id_hex

    # 1. Загружаем первую версию
    content_a = b"Version A"
    files_a = {"file": ("file_a.txt", content_a, "text/plain")}
    response_a = client.post(
        f"/storage/store?id_hex={file_id}", files=files_a, headers=auth_headers
    )
    assert response_a.status_code == 200
    cid_a = response_a.json()["cid"]

    # 2. Загружаем вторую версию
    content_b = b"Version B is different"
    files_b = {"file": ("file_b.txt", content_b, "text/plain")}
    response_b = client.post(
        f"/storage/store?id_hex={file_id}", files=files_b, headers=auth_headers
    )
    assert response_b.status_code == 200
    cid_b = response_b.json()["cid"]

    assert cid_a != cid_b, "Different content should produce different CIDs"

    # 3. Проверяем версии
    response_versions = client.get(f"/storage/versions/{file_id}", headers=auth_headers)
    assert response_versions.status_code == 200
    versions = response_versions.json()

    assert isinstance(versions, list)
    assert len(versions) >= 2, "There should be at least two versions for the file"

    # Проверяем, что наши CIDs присутствуют в списке версий
    found_cids = {v["cid"] for v in versions}
    assert cid_a in found_cids
    assert cid_b in found_cids

    # Проверяем структуру одного из элементов
    last_version = versions[-1]
    assert last_version["cid"] == cid_b
    assert last_version["size"] == len(content_b)


# --- Негативные кейсы для Storage ---


def test_store_empty_file(client: httpx.Client, auth_headers: dict):
    """
    5.4. Попытка загрузить пустой файл.
    """
    files = {"file": ("empty.txt", b"", "text/plain")}
    response = client.post("/storage/store", files=files, headers=auth_headers)
    # Ожидаем ошибку валидации
    assert response.status_code == 422  # Или 400, в зависимости от реализации
    assert "empty_file" in response.text or "size must be > 0" in response.text


def test_bad_id_in_cid_endpoint(client: httpx.Client, auth_headers: dict):
    """
    5.4. Запрос CID с невалидным форматом id_hex.
    """
    bad_id = "0x123"
    response = client.get(f"/storage/cid/{bad_id}", headers=auth_headers)
    assert response.status_code == 400
    assert "bad_id" in response.text


def test_cid_not_found(client: httpx.Client, auth_headers: dict, random_id_hex: str):
    """
    5.4. Запрос CID для несуществующего id_hex.
    """
    not_found_id = random_id_hex
    response = client.get(f"/storage/cid/{not_found_id}", headers=auth_headers)
    assert response.status_code in [404, 400]
    assert "not_found" in response.text