import sys
import time
from pathlib import Path

# Add project root (bot/) to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.security.hmac import sign, verify


def test_sign_creates_valid_signature():
    """Test: sign creates a valid signature."""
    secret = "test_secret_key"
    payload = {"cmd": "test", "data": "value"}

    signed = sign(payload, secret)

    # Check format: payload.signature
    assert "." in signed
    parts = signed.split(".", 1)
    assert len(parts) == 2

    # Check that it can be decoded
    verified = verify(signed, secret)
    assert verified is not None
    assert verified["cmd"] == "test"
    assert verified["data"] == "value"


def test_verify_accepts_valid_signature():
    """Test: verify accepts a valid signature."""
    secret = "test_secret_key"
    payload = {"cmd": "page", "cursor": "12345"}

    signed = sign(payload, secret)
    verified = verify(signed, secret)

    assert verified is not None
    assert verified["cmd"] == "page"
    assert verified["cursor"] == "12345"
    assert "ts" in verified  # timestamp should be added


def test_verify_rejects_invalid_signature():
    """Test: verify rejects an invalid signature."""
    secret = "test_secret_key"
    payload = {"cmd": "test"}

    signed = sign(payload, secret)

    # Wrong secret
    verified_wrong_secret = verify(signed, "wrong_secret")
    assert verified_wrong_secret is None

    # Corrupted signature
    corrupted = signed[:-5] + "xxxxx"
    verified_corrupted = verify(corrupted, secret)
    assert verified_corrupted is None

    # Wrong format (no dot)
    verified_no_dot = verify("invalid_data", secret)
    assert verified_no_dot is None


def test_verify_rejects_expired_signature():
    """Test: verify rejects an expired signature."""
    secret = "test_secret_key"
    payload = {"cmd": "test", "ts": int(time.time()) - 100}  # 100 seconds ago

    signed = sign(payload, secret, ttl_seconds=60)
    verified = verify(signed, secret, ttl_seconds=60)

    assert verified is None  # It should be rejected


def test_verify_accepts_fresh_signature():
    """Test: verify accepts a fresh signature."""
    secret = "test_secret_key"
    payload = {"cmd": "test", "ts": int(time.time())}  # Now

    signed = sign(payload, secret, ttl_seconds=60)
    verified = verify(signed, secret, ttl_seconds=60)

    assert verified is not None
    assert verified["cmd"] == "test"


def test_sign_adds_timestamp_if_missing():
    """Test: sign adds timestamp if it's missing."""
    secret = "test_secret_key"
    payload = {"cmd": "test"}

    signed = sign(payload, secret)
    verified = verify(signed, secret)

    assert verified is not None
    assert "ts" in verified
    assert isinstance(verified["ts"], (int, float))


def test_sign_preserves_existing_timestamp():
    """Test: sign preserves existing timestamp."""
    secret = "test_secret_key"
    # Use current timestamp to avoid TTL issues
    custom_ts = int(time.time())
    payload = {"cmd": "test", "ts": custom_ts}

    signed = sign(payload, secret)
    verified = verify(signed, secret, ttl_seconds=999999)

    assert verified is not None
    assert verified["ts"] == custom_ts


def test_verify_handles_complex_payload():
    """Test: verify handles a complex payload."""
    secret = "test_secret_key"
    payload = {
        "cmd": "open",
        "file_id": "0x1234567890abcdef",
        "cursor": "cursor_value",
        "nested": {"key": "value"},
    }

    signed = sign(payload, secret)
    verified = verify(signed, secret)

    assert verified is not None
    assert verified["cmd"] == "open"
    assert verified["file_id"] == "0x1234567890abcdef"
    assert verified["cursor"] == "cursor_value"
    assert verified["nested"]["key"] == "value"
