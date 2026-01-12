import httpx
import pytest

# Assume conftest.py is in the same folder
# and defines fixtures client, auth_headers, test_signer, random_id_hex

pytestmark = pytest.mark.e2e

# --- Negative cases for Storage ---


def test_store_empty_file(client: httpx.Client, auth_headers: dict):
    """
    5.4. Attempt to upload an empty file.
    """
    files = {"file": ("empty.txt", b"", "text/plain")}
    response = client.post("/storage/store", files=files, headers=auth_headers)
    assert response.status_code == 400
    assert "empty_file" in response.text


def test_bad_id_in_cid_endpoint(client: httpx.Client, auth_headers: dict):
    """
    5.4. Request CID with invalid id_hex format.
    """
    bad_id = "0x123"
    response = client.get(f"/storage/cid/{bad_id}", headers=auth_headers)
    assert response.status_code == 400
    assert "bad_id" in response.text


def test_cid_not_found(client: httpx.Client, auth_headers: dict, random_id_hex: str):
    """
    5.4. Request CID for non-existent id_hex.
    """
    not_found_id = random_id_hex
    response = client.get(f"/storage/cid/{not_found_id}", headers=auth_headers)
    assert response.status_code in [404, 400]
    assert "not_found" in response.text
