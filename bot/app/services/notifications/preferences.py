"""User notification preferences (subscribe/unsubscribe, quiet hours)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis import asyncio as aioredis

from ...config import settings

logger = logging.getLogger(__name__)


def _parse_hhmm(value: str) -> int:
    hours, _, minutes = value.partition(":")
    return int(hours) * 60 + int(minutes)


def _format_hhmm(total_minutes: int) -> str:
    total_minutes = total_minutes % (24 * 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


@dataclass
class QuietHours:
    """Quiet hours window in minutes from midnight (UTC)."""

    start_min: int
    end_min: int

    @classmethod
    def parse(cls, value: str) -> "QuietHours":
        """Parses string like '23:00-07:00'."""
        start_raw, _, end_raw = value.partition("-")
        return cls(start_min=_parse_hhmm(start_raw), end_min=_parse_hhmm(end_raw))

    def contains(self, ts: datetime) -> bool:
        minute = (ts.hour * 60) + ts.minute
        if self.start_min == self.end_min:
            return False  # disabled
        if self.start_min < self.end_min:
            return self.start_min <= minute < self.end_min
        # wraps midnight
        return minute >= self.start_min or minute < self.end_min

    def seconds_until_end(self, ts: datetime) -> int:
        """Returns number of seconds until quiet period ends (>=0)."""
        minute = (ts.hour * 60) + ts.minute
        if not self.contains(ts):
            return 0
        if self.start_min < self.end_min:
            end_minute = self.end_min
        else:
            # wraps midnight
            end_minute = self.end_min + (24 * 60 if minute >= self.start_min else 0)
        current_total = minute
        if end_minute <= current_total:
            end_minute += 24 * 60
        minutes_left = end_minute - current_total
        return int(timedelta(minutes=minutes_left).total_seconds())

    def serialize(self) -> str:
        return f"{_format_hhmm(self.start_min)}-{_format_hhmm(self.end_min)}"


class NotificationPreferences:
    """Stores per-chat notification settings in Redis."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client
        self.default_subscribed = settings.NOTIFY_DEFAULT_SUBSCRIBED

    @staticmethod
    def _subscribed_key(chat_id: int) -> str:
        return f"tg:subscribed:{chat_id}"

    @staticmethod
    def _quiet_key(chat_id: int) -> str:
        return f"tg:quiet_hours:{chat_id}"

    async def is_subscribed(self, chat_id: int) -> bool:
        """Returns True if chat opted-in (default True)."""
        try:
            raw = await self.redis.get(self._subscribed_key(chat_id))
            if raw is None:
                return self.default_subscribed
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode()
            return str(raw) != "0"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read subscription flag: %s", exc)
            return self.default_subscribed

    async def set_subscribed(self, chat_id: int, subscribed: bool) -> None:
        try:
            await self.redis.set(self._subscribed_key(chat_id), "1" if subscribed else "0")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to store subscription flag: %s", exc)

    async def get_quiet_hours(self, chat_id: int) -> QuietHours | None:
        try:
            raw = await self.redis.get(self._quiet_key(chat_id))
            if raw is None:
                return None
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode()
            raw_str = str(raw)
            if "-" not in raw_str:
                return None
            return QuietHours.parse(raw_str)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read quiet hours: %s", exc)
            return None

    async def set_quiet_hours(self, chat_id: int, quiet: QuietHours) -> None:
        try:
            await self.redis.set(self._quiet_key(chat_id), quiet.serialize())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to store quiet hours: %s", exc)

    async def clear_quiet_hours(self, chat_id: int) -> None:
        try:
            await self.redis.delete(self._quiet_key(chat_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to clear quiet hours: %s", exc)

    async def is_quiet_now(self, chat_id: int, ts: datetime | None = None) -> tuple[bool, int]:
        """Returns (quiet_now, delay_seconds_to_end)."""
        ts = ts or datetime.now(UTC)
        quiet = await self.get_quiet_hours(chat_id)
        if not quiet:
            return False, 0
        return quiet.contains(ts), quiet.seconds_until_end(ts)
