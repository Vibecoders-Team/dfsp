import hmac
import hashlib


def verify_hmac(signature: str, body: bytes, secret: str) -> bool:
    """
    Заглушка под будущую проверку подписи вебхука.
    Сейчас просто считает sha256-hmac и сравнивает строки.
    """
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # в реальности формат сигнатуры может быть другим
    return hmac.compare_digest(mac, signature)
