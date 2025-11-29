"""Утилиты для работы с webhook URL бота."""


def build_webhook_url(origin: str, secret: str) -> str:
    """Собирает полный URL webhook по origin и секрету."""
    base = str(origin).rstrip("/")
    return f"{base}/tg/webhook/{secret}"


def mask_webhook_url(url: str, secret: str) -> str:
    """Маскирует секрет в webhook URL для безопасного логирования."""
    return url.replace(secret, "***") if secret else url
