import sys
import time
from pathlib import Path

# Добавляем корень проекта (bot/) в sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.security.hmac import sign, verify


def test_sign_creates_valid_signature():
    """Тест: sign создает валидную подпись."""
    secret = "test_secret_key"
    payload = {"cmd": "test", "data": "value"}

    signed = sign(payload, secret)

    # Проверяем формат: payload.signature
    assert "." in signed
    parts = signed.split(".", 1)
    assert len(parts) == 2

    # Проверяем, что можно декодировать
    verified = verify(signed, secret)
    assert verified is not None
    assert verified["cmd"] == "test"
    assert verified["data"] == "value"


def test_verify_accepts_valid_signature():
    """Тест: verify принимает валидную подпись."""
    secret = "test_secret_key"
    payload = {"cmd": "page", "cursor": "12345"}

    signed = sign(payload, secret)
    verified = verify(signed, secret)

    assert verified is not None
    assert verified["cmd"] == "page"
    assert verified["cursor"] == "12345"
    assert "ts" in verified  # timestamp должен быть добавлен


def test_verify_rejects_invalid_signature():
    """Тест: verify отклоняет невалидную подпись."""
    secret = "test_secret_key"
    payload = {"cmd": "test"}

    signed = sign(payload, secret)

    # Неправильный секрет
    verified_wrong_secret = verify(signed, "wrong_secret")
    assert verified_wrong_secret is None

    # Поврежденная подпись
    corrupted = signed[:-5] + "xxxxx"
    verified_corrupted = verify(corrupted, secret)
    assert verified_corrupted is None

    # Неправильный формат (нет точки)
    verified_no_dot = verify("invalid_data", secret)
    assert verified_no_dot is None


def test_verify_rejects_expired_signature():
    """Тест: verify отклоняет просроченную подпись."""
    secret = "test_secret_key"
    payload = {"cmd": "test", "ts": int(time.time()) - 100}  # 100 секунд назад

    signed = sign(payload, secret, ttl_seconds=60)
    verified = verify(signed, secret, ttl_seconds=60)

    assert verified is None  # Должна быть отклонена


def test_verify_accepts_fresh_signature():
    """Тест: verify принимает свежую подпись."""
    secret = "test_secret_key"
    payload = {"cmd": "test", "ts": int(time.time())}  # Сейчас

    signed = sign(payload, secret, ttl_seconds=60)
    verified = verify(signed, secret, ttl_seconds=60)

    assert verified is not None
    assert verified["cmd"] == "test"


def test_sign_adds_timestamp_if_missing():
    """Тест: sign добавляет timestamp если его нет."""
    secret = "test_secret_key"
    payload = {"cmd": "test"}

    signed = sign(payload, secret)
    verified = verify(signed, secret)

    assert verified is not None
    assert "ts" in verified
    assert isinstance(verified["ts"], (int, float))


def test_sign_preserves_existing_timestamp():
    """Тест: sign сохраняет существующий timestamp."""
    secret = "test_secret_key"
    # Используем текущий timestamp, чтобы не было проблем с TTL
    custom_ts = int(time.time())
    payload = {"cmd": "test", "ts": custom_ts}

    signed = sign(payload, secret)
    verified = verify(signed, secret, ttl_seconds=999999)

    assert verified is not None
    assert verified["ts"] == custom_ts


def test_verify_handles_complex_payload():
    """Тест: verify обрабатывает сложный payload."""
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
