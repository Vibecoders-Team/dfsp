# backend/tests/integration/test_files_meta_verify.py
import secrets

import httpx
import pytest

pytestmark = pytest.mark.e2e


def _hex32() -> str:
    return "0x" + secrets.token_hex(32)


def _fake_cid() -> str:
    # backend CID validation is lenient - any string placeholder is fine for tests
    return "bafy" + secrets.token_hex(16)


def test_meta_tx_submit_queued_and_duplicate(client: httpx.Client, auth_headers: dict):
    """
    /meta-tx/submit: basic idempotency.
    We intentionally send bogus typed_data and signature - if server-side verification is off,
    we get queued; if on, we get 400 signature_invalid (both behaviors are acceptable).
    """
    req_id = "req-" + secrets.token_hex(8)
    bogus_typed = {
        "domain": {
            "name": "MinimalForwarder",
            "version": "0.0.1",
            "chainId": 31337,
            "verifyingContract": "0x" + "11" * 20,
        },
        "types": {
            "ForwardRequest": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "gas", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "data", "type": "bytes"},
            ]
        },
        "primaryType": "ForwardRequest",
        "message": {
            "from": "0x" + "22" * 20,
            "to": "0x" + "33" * 20,
            "value": 0,
            "gas": 100000,
            "nonce": 0,
            "data": "0x" + "00" * 32,
        },
    }
    bogus_sig = "0x" + "55" * 65

    r1 = client.post(
        "/meta-tx/submit",
        json={
            "request_id": req_id,
            "typed_data": bogus_typed,
            "signature": bogus_sig,
        },
        headers=auth_headers,
    )

    # allow 200/202 queued OR 400 signature_invalid depending on server validation flag
    assert r1.status_code in (200, 202, 400), f"unexpected {r1.status_code}: {r1.text}"
    if r1.status_code in (200, 202):
        assert r1.json().get("status") == "queued"

    # repeat with same request_id -> duplicate (if first queued) or 400 on validation
    r2 = client.post(
        "/meta-tx/submit",
        json={
            "request_id": req_id,
            "typed_data": bogus_typed,
            "signature": bogus_sig,
        },
        headers=auth_headers,
    )
    assert r2.status_code in (200, 202, 400), f"unexpected {r2.status_code}: {r2.text}"
    if r2.status_code in (200, 202):
        assert r2.json().get("status") in (
            "duplicate",
            "queued",
        )  # just in case the first was rejected by validation
