"""Диагностические утилиты для проверки конфигурации."""

import logging
from urllib.parse import urlparse

from ..config import settings

logger = logging.getLogger(__name__)


def check_public_web_origin() -> tuple[bool, str]:
    """
    Проверяет корректность настройки PUBLIC_WEB_ORIGIN.

    Returns:
        (is_valid, error_message)
    """
    try:
        origin = str(settings.PUBLIC_WEB_ORIGIN)
        parsed = urlparse(origin)

        # Проверка что это валидный URL
        if not parsed.scheme:
            return False, "PUBLIC_WEB_ORIGIN должен начинаться с http:// или https://"  # noqa: RUF001

        if parsed.scheme not in ("http", "https"):
            return False, f"PUBLIC_WEB_ORIGIN должен использовать http:// или https://, получен {parsed.scheme}://"

        # Проверка на localhost (может быть проблемой если бот доступен извне)
        hostname = parsed.hostname or ""
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0"):  # noqa: S104
            return (
                False,
                f"PUBLIC_WEB_ORIGIN указывает на {hostname} - это может быть недоступно для пользователей. "
                "Используйте публичный IP или домен.",
            )

        # Проверка что есть hostname
        if not hostname:
            return False, "PUBLIC_WEB_ORIGIN должен содержать hostname (например, example.com или 192.168.1.100)"

        return True, "OK"

    except Exception as e:
        return False, f"Ошибка при проверке PUBLIC_WEB_ORIGIN: {e}"


def print_config_diagnostics() -> None:
    """Выводит диагностическую информацию о конфигурации."""
    logger.info("=== Диагностика конфигурации ===")

    # Проверка PUBLIC_WEB_ORIGIN
    is_valid, message = check_public_web_origin()
    logger.info("PUBLIC_WEB_ORIGIN: %s", settings.PUBLIC_WEB_ORIGIN)
    if is_valid:
        logger.info("  ✅ %s", message)
    else:
        logger.warning("  ❌ %s", message)

    # Проверка DFSP_API_URL
    logger.info("DFSP_API_URL: %s", settings.DFSP_API_URL)

    # Пример ссылки для линка
    origin = str(settings.PUBLIC_WEB_ORIGIN).rstrip("/")
    logger.info("Пример ссылки для линка: %s/tg/link?token=EXAMPLE_TOKEN", origin)
