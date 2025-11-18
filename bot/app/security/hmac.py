import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any


def verify_hmac(signature: str, body: bytes, secret: str) -> bool:
    """
    Заглушка под будущую проверку подписи вебхука.
    Сейчас просто считает sha256-hmac и сравнивает строки.
    """
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # в реальности формат сигнатуры может быть другим
    return hmac.compare_digest(mac, signature)


def _base64url_encode(data: bytes) -> str:
    """Кодирует bytes в base64url без padding."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    """Декодирует base64url строку в bytes."""
    # Добавляем padding если нужно
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
    Подписывает payload для callback_data.

    Формат: base64url(JSON {cmd, cursor, ts}) + '.' + HMAC-SHA256(secret)

    Args:
        payload: словарь с данными (cmd, cursor, ts и т.д.)
        secret: секретный ключ для HMAC
        ttl_seconds: время жизни подписи в секундах (по умолчанию 60)

    Returns:
        Подписанная строка в формате: base64url(payload) + '.' + base64url(signature)
    Note:
        signature_bytes можно указать, чтобы укоротить подпись (по умолчанию полный HMAC-SHA256).
    """
    # Добавляем timestamp если его нет
    if "ts" not in payload:
        payload = payload.copy()
        payload["ts"] = int(datetime.now(UTC).timestamp())

    # Кодируем payload в JSON и затем в base64url
    json_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    json_bytes = json_str.encode("utf-8")
    encoded_payload = _base64url_encode(json_bytes)

    # Вычисляем HMAC-SHA256 подпись
    mac = hmac.new(secret.encode("utf-8"), json_bytes, hashlib.sha256).digest()
    if signature_bytes is not None:
        mac = mac[:signature_bytes]
    encoded_signature = _base64url_encode(mac)

    # Возвращаем payload + '.' + signature
    return f"{encoded_payload}.{encoded_signature}"


def verify(
    payload_and_sig: str,
    secret: str,
    ttl_seconds: int = 60,
    signature_bytes: int | None = None,
) -> dict[str, Any] | None:
    """
    Проверяет подпись callback_data и возвращает payload если подпись валидна.

    Args:
        payload_and_sig: строка в формате base64url(payload) + '.' + base64url(signature)
        secret: секретный ключ для HMAC
        ttl_seconds: время жизни подписи в секундах (по умолчанию 60)

    Returns:
        Распарсенный payload (dict) если подпись валидна и не истекла, иначе None
    """
    try:
        # Разделяем payload и signature
        if "." not in payload_and_sig:
            return None

        encoded_payload, encoded_signature = payload_and_sig.rsplit(".", 1)

        # Декодируем payload
        json_bytes = _base64url_decode(encoded_payload)
        json_str = json_bytes.decode("utf-8")
        payload = json.loads(json_str)

        # Проверяем timestamp (TTL)
        if "ts" in payload:
            ts = payload["ts"]
            if isinstance(ts, (int, float)):
                payload_time = datetime.fromtimestamp(ts, tz=UTC)
                now = datetime.now(UTC)
                age = (now - payload_time).total_seconds()

                if age > ttl_seconds:
                    return None  # Подпись истекла

        # Вычисляем ожидаемую подпись
        expected_signature_bytes = hmac.new(secret.encode("utf-8"), json_bytes, hashlib.sha256).digest()
        if signature_bytes is not None:
            expected_signature_bytes = expected_signature_bytes[:signature_bytes]
        expected_signature = _base64url_encode(expected_signature_bytes)

        # Сравниваем подписи безопасным способом
        if not hmac.compare_digest(encoded_signature, expected_signature):
            return None  # Подпись не совпадает

        return payload

    except Exception:
        # Любая ошибка при декодировании/проверке означает невалидную подпись
        return None
