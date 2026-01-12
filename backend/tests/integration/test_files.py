import secrets

import httpx
import pytest
from web3 import Web3

from .conftest import is_hex_bytes32

pytestmark = pytest.mark.e2e


def _hex32() -> str:
    return "0x" + secrets.token_hex(32)


def _fake_cid() -> str:
    # backend CID validation is lenient - any string placeholder is fine for tests
    return "bafy" + secrets.token_hex(16)


def test_files_create_typeddata_ok(client: httpx.Client, auth_headers: dict):
    """
    /files: happy-path - returns correct EIP-712 typedData (ForwardRequest)
    """
    payload = {
        "fileId": _hex32(),
        "name": f"report-{secrets.token_hex(4)}.pdf",
        "size": 123456,
        "mime": "application/pdf",
        "cid": _fake_cid(),
        "checksum": _hex32(),
    }
    r = client.post("/files", json=payload, headers=auth_headers)
    assert r.status_code == 200, f"unexpected {r.status_code}: {r.text}"

    body = r.json()
    assert "typedData" in body, f"no typedData in response: {body}"
    td = body["typedData"]

    # basic EIP-712 shape
    assert isinstance(td.get("domain"), dict)
    assert isinstance(td.get("types"), dict)
    assert td.get("primaryType") == "ForwardRequest"
    assert isinstance(td.get("message"), dict)

    # domain
    dom = td["domain"]
    # allow both chainId forms: int/str
    assert int(dom.get("chainId", 0)) > 0
    assert dom.get("name") in ("MinimalForwarder",)  # per spec
    assert isinstance(dom.get("verifyingContract"), str) and dom["verifyingContract"].startswith("0x")

    # types
    fr = td["types"].get("ForwardRequest")
    assert isinstance(fr, list) and any(x.get("name") == "from" for x in fr)

    # message
    msg = td["message"]
    assert Web3.is_address(msg.get("from", "")), f"bad from: {msg.get('from')}"
    assert Web3.is_address(msg.get("to", "")), f"bad to: {msg.get('to')}"
    assert isinstance(msg.get("gas"), int) or str(msg.get("gas", "")).isdigit()
    assert is_hex_bytes32(msg.get("data", "")), "message.data must be 0x.. hex"


def test_files_duplicate_checksum_per_owner_409(client: httpx.Client, auth_headers: dict):
    """
    /files: second file with same checksum for same owner -> 409
    """
    checksum = _hex32()
    first = {
        "fileId": _hex32(),
        "name": "a.txt",
        "size": 10,
        "mime": "text/plain",
        "cid": _fake_cid(),
        "checksum": checksum,
    }
    r1 = client.post("/files", json=first, headers=auth_headers)
    assert r1.status_code == 200, r1.text

    second = {
        "fileId": _hex32(),  # different id, same checksum
        "name": "b.txt",
        "size": 11,
        "mime": "text/plain",
        "cid": _fake_cid(),
        "checksum": checksum,
    }
    r2 = client.post("/files", json=second, headers=auth_headers)
    assert r2.status_code == 409, f"expected 409 duplicate, got {r2.status_code}: {r2.text}"
    assert "duplicate_checksum" in r2.text


def test_files_bad_hex_inputs_400(client: httpx.Client, auth_headers: dict):
    """
    /files: invalid fileId/checksum format -> 400
    """
    bad = {
        "fileId": "0x1234",
        "name": "bad.bin",
        "size": 1,
        "mime": "application/octet-stream",
        "cid": _fake_cid(),
        "checksum": "0xdeadbeef",
    }
    r = client.post("/files", json=bad, headers=auth_headers)
    assert r.status_code == 400
    # error code can vary: bad_file_id / bad_checksum - 400 is sufficient
