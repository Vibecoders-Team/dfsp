"""Utilities for working with bot webhook URLs."""


def build_webhook_url(origin: str, secret: str) -> str:
    """Build full webhook URL from origin and secret."""
    base = str(origin).rstrip("/")
    return f"{base}/tg/webhook/{secret}"


def mask_webhook_url(url: str, secret: str) -> str:
    """Mask secret in webhook URL for safe logging."""
    return url.replace(secret, "***") if secret else url
