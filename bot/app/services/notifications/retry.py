"""Retry logic with exponential backoff for Telegram API."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from ...metrics import (
    tg_notify_send_latency_seconds,
    tg_outbound_rate_limited_total,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryConfig:
    """Retry configuration."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        backoff_multiplier: float = 2.0,
    ) -> None:
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier


async def send_with_retry(
    bot: Bot,
    chat_id: int,
    text: str,
    config: RetryConfig | None = None,
) -> bool:
    """
    Send message with retry and exponential backoff.

    Handles:
    - TelegramRetryAfter (429) - waits for retry_after
    - TelegramAPIError (5xx) - retries with backoff
    - Other errors - logs and returns False

    Returns True if sent successfully, False otherwise.
    """
    if config is None:
        config = RetryConfig()

    backoff = config.initial_backoff
    start_time = time.time()

    for attempt in range(config.max_retries + 1):
        try:
            await bot.send_message(chat_id=chat_id, text=text)
            # Record latency on success
            latency = time.time() - start_time
            tg_notify_send_latency_seconds.observe(latency)
            return True
        except TelegramRetryAfter as e:
            # Rate limit - wait for retry_after seconds
            tg_outbound_rate_limited_total.inc()
            retry_after = e.retry_after or 60
            logger.warning(
                "Rate limited (429) for chat %d, waiting %d seconds (attempt %d/%d)",
                chat_id,
                retry_after,
                attempt + 1,
                config.max_retries + 1,
            )
            if attempt < config.max_retries:
                await asyncio.sleep(retry_after)
                continue
            # Record latency even on failure
            latency = time.time() - start_time
            tg_notify_send_latency_seconds.observe(latency)
            logger.error("Failed to send after rate limit retries for chat %d", chat_id)
            return False
        except TelegramAPIError as e:
            # 5xx or other API errors - retry with backoff
            if attempt < config.max_retries:
                logger.warning(
                    "Telegram API error for chat %d (attempt %d/%d): %s, retrying in %.1f seconds",
                    chat_id,
                    attempt + 1,
                    config.max_retries + 1,
                    e,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * config.backoff_multiplier, config.max_backoff)
                continue
            logger.error("Failed to send after retries for chat %d: %s", chat_id, e)
            # Record latency even on failure
            latency = time.time() - start_time
            tg_notify_send_latency_seconds.observe(latency)
            return False
        except Exception as e:
            # Unexpected error - don't retry
            # Record latency even on failure
            latency = time.time() - start_time
            tg_notify_send_latency_seconds.observe(latency)
            logger.error("Unexpected error sending to chat %d: %s", chat_id, e, exc_info=True)
            return False

    # Record latency if we exhausted all retries
    latency = time.time() - start_time
    tg_notify_send_latency_seconds.observe(latency)
    return False


async def execute_with_retry(  # noqa: UP047
    func: Callable[[], Awaitable[T]],
    config: RetryConfig | None = None,
) -> T | None:
    """
    Execute function with retry and exponential backoff.

    Generic retry wrapper for any async function.
    """
    if config is None:
        config = RetryConfig()

    backoff = config.initial_backoff

    for attempt in range(config.max_retries + 1):
        try:
            return await func()
        except TelegramRetryAfter as e:
            retry_after = e.retry_after or 60
            logger.warning(
                "Rate limited (429), waiting %d seconds (attempt %d/%d)",
                retry_after,
                attempt + 1,
                config.max_retries + 1,
            )
            if attempt < config.max_retries:
                await asyncio.sleep(retry_after)
                continue
            return None
        except TelegramAPIError as e:
            if attempt < config.max_retries:
                logger.warning(
                    "API error (attempt %d/%d): %s, retrying in %.1f seconds",
                    attempt + 1,
                    config.max_retries + 1,
                    e,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * config.backoff_multiplier, config.max_backoff)
                continue
            logger.error("Failed after retries: %s", e)
            return None
        except Exception as e:
            logger.error("Unexpected error: %s", e, exc_info=True)
            return None

    return None
