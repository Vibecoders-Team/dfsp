import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any


def verify_hmac(signature: str, body: bytes, secret: str) -> bool:
    """
    Stub for future webhook signature verification.
    Currently just calculates sha256-hmac and compares strings.
    """
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # in reality, the signature format may be different
    return hmac.compare_digest(mac, signature)


def _base64url_encode(data: bytes) -> str:
    """Encodes bytes to base64url without padding."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    """Decodes a base64url string to bytes."""
    # Add padding if needed
    padding = len(data) % 4
    if padding:
        data += "=" * (4 - padding)
    return base64.urlsafe_b64decode(data)


def sign(
    payload: dict[str, Any],
    secret: str,
    ttl_seconds: int = 60,
    signature_bytes: int | None = None,
) -> str:
    """
    Signs the payload for callback_data.

    Format: base64url(JSON {cmd, cursor, ts}) + '.' + HMAC-SHA256(secret)

    Args:
        payload: dictionary with data (cmd, cursor, ts, etc.)
        secret: secret key for HMAC
        ttl_seconds: signature lifetime in seconds (default 60)

    Returns:
        Signed string in the format: base64url(payload) + '.' + base64url(signature)
    Note:
        signature_bytes can be specified to shorten the signature (default is full HMAC-SHA256).
    """
    # Add timestamp if it's not there
    if "ts" not in payload:
        payload = payload.copy()
        payload["ts"] = int(datetime.now(UTC).timestamp())

    # Encode payload to JSON and then to base64url
    json_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    json_bytes = json_str.encode("utf-8")
    encoded_payload = _base64url_encode(json_bytes)

    # Calculate HMAC-SHA256 signature
    mac = hmac.new(secret.encode("utf-8"), json_bytes, hashlib.sha256).digest()
    if signature_bytes is not None:
        mac = mac[:signature_bytes]
    encoded_signature = _base64url_encode(mac)

    # Return payload + '.' + signature
    return f"{encoded_payload}.{encoded_signature}"


def verify(
    payload_and_sig: str,
    secret: str,
    ttl_seconds: int = 60,
    signature_bytes: int | None = None,
) -> dict[str, Any] | None:
    """
    Verifies the callback_data signature and returns the payload if the signature is valid.

    Args:
        payload_and_sig: string in the format base64url(payload) + '.' + base64url(signature)
        secret: secret key for HMAC
        ttl_seconds: signature lifetime in seconds (default 60)

    Returns:
        Parsed payload (dict) if the signature is valid and not expired, otherwise None
    """
    try:
        # Split payload and signature
        if "." not in payload_and_sig:
            return None

        encoded_payload, encoded_signature = payload_and_sig.rsplit(".", 1)

        # Decode payload
        json_bytes = _base64url_decode(encoded_payload)
        json_str = json_bytes.decode("utf-8")
        payload = json.loads(json_str)

        # Check timestamp (TTL)
        if "ts" in payload:
            ts = payload["ts"]
            if isinstance(ts, (int, float)):
                payload_time = datetime.fromtimestamp(ts, tz=UTC)
                now = datetime.now(UTC)
                age = (now - payload_time).total_seconds()

                if age > ttl_seconds:
                    return None  # signature expired

        # Compute expected signature
        expected_signature_bytes = hmac.new(secret.encode("utf-8"), json_bytes, hashlib.sha256).digest()
        if signature_bytes is not None:
            expected_signature_bytes = expected_signature_bytes[:signature_bytes]
        expected_signature = _base64url_encode(expected_signature_bytes)

        # Compare signatures safely
        if not hmac.compare_digest(encoded_signature, expected_signature):
            return None  # signature mismatch

        return payload

    except Exception:
        # Any decode/verify error means invalid signature
        return None
