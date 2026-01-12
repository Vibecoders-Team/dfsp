"""Diagnostic utilities for configuration checks."""

import logging
from urllib.parse import urlparse

from ..config import settings
from .webhook import build_webhook_url, mask_webhook_url

logger = logging.getLogger(__name__)


def check_public_web_origin() -> tuple[bool, str]:
    """
    Check validity of PUBLIC_WEB_ORIGIN.

    Returns:
        (is_valid, error_message)
    """
    try:
        origin = str(settings.PUBLIC_WEB_ORIGIN)
        parsed = urlparse(origin)

        # Check that this is a valid URL
        if not parsed.scheme:
            return False, "PUBLIC_WEB_ORIGIN must start with http:// or https://"  # noqa: RUF001

        if parsed.scheme not in ("http", "https"):
            return False, f"PUBLIC_WEB_ORIGIN must use http:// or https://, got {parsed.scheme}://"

        # Check for localhost (can be a problem if bot is accessible externally)
        hostname = parsed.hostname or ""
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0"):  # noqa: S104
            return (
                False,
                f"PUBLIC_WEB_ORIGIN points to {hostname} - this may be unreachable for users. "
                "Use a public IP or domain.",
            )

        # Check that hostname exists
        if not hostname:
            return False, "PUBLIC_WEB_ORIGIN must include a hostname (e.g., example.com or 192.168.1.100)"

        return True, "OK"

    except Exception as e:
        return False, f"Error while checking PUBLIC_WEB_ORIGIN: {e}"


def print_config_diagnostics() -> None:
    """Print diagnostic configuration info."""
    logger.info("=== Configuration diagnostics ===")

    # Check PUBLIC_WEB_ORIGIN
    is_valid, message = check_public_web_origin()
    logger.info("PUBLIC_WEB_ORIGIN: %s", settings.PUBLIC_WEB_ORIGIN)
    if is_valid:
        logger.info("  ✅ %s", message)
    else:
        logger.warning("  ❌ %s", message)

    # Check DFSP_API_URL
    logger.info("DFSP_API_URL: %s", settings.DFSP_API_URL)
    logger.info("BOT_DB_DSN: %s (lang=%s)", settings.BOT_DB_DSN, settings.BOT_DEFAULT_LANGUAGE)

    # Example link URL
    origin = str(settings.PUBLIC_WEB_ORIGIN).rstrip("/")
    logger.info("Example link URL: %s/tg/link?token=EXAMPLE_TOKEN", origin)

    # Webhook URL (without explicit secret in logs)
    webhook_url = build_webhook_url(settings.PUBLIC_WEB_ORIGIN, settings.WEBHOOK_SECRET)
    logger.info("Webhook URL: %s", mask_webhook_url(webhook_url, settings.WEBHOOK_SECRET))
