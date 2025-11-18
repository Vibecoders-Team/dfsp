from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis

logger = logging.getLogger(__name__)

JSONType = dict[str, object] | list[object] | str | int | float | bool | None


class Cache:
    @staticmethod
    def _rds() -> redis.Redis:
        try:
            # Lazy import to avoid circular dependency during app startup
            from app.deps import rds as _rds  # type: ignore

            return _rds
        except Exception:
            # Fallback: construct a temporary client from env if deps is not ready
            import os

            import redis  # type: ignore

            url = os.getenv("REDIS_URL") or os.getenv("REDIS_DSN") or "redis://localhost:6379/0"
            try:
                return redis.from_url(url, decode_responses=True)
            except Exception as e:
                logger.warning("Failed to create fallback redis client: %s", e, exc_info=True)
                raise

    @staticmethod
    def get_text(key: str) -> str | None:
        try:
            val = Cache._rds().get(key)
            if val is None:
                return None
            if isinstance(val, (bytes, bytearray)):
                return val.decode("utf-8", errors="ignore")
            return str(val)
        except Exception:
            logger.debug("Cache.get_text failed for key=%s", key, exc_info=True)
            return None

    @staticmethod
    def set_text(key: str, value: str, ttl: int) -> None:
        try:
            Cache._rds().setex(key, int(ttl), value)
        except Exception:
            logger.warning("Cache.set_text failed for key=%s: %s", key, value, exc_info=True)

    @staticmethod
    def get_json(key: str) -> JSONType | None:
        txt = Cache.get_text(key)
        if not txt:
            return None
        try:
            return json.loads(txt)
        except Exception:
            logger.debug("Cache.get_json failed to decode JSON for key=%s", key, exc_info=True)
            return None

    @staticmethod
    def set_json(key: str, value: JSONType, ttl: int) -> None:
        try:
            Cache.set_text(key, json.dumps(value, separators=(",", ":")), ttl)
        except Exception:
            logger.warning("Cache.set_json failed for key=%s: %s", key, value, exc_info=True)

    @staticmethod
    def delete(key: str) -> None:
        try:
            Cache._rds().delete(key)
        except Exception:
            logger.warning("Cache.delete failed for key=%s", key, exc_info=True)

    @staticmethod
    def remember_json(key: str, ttl: int, producer: Callable[[], JSONType]) -> JSONType | None:
        cached = Cache.get_json(key)
        if cached is not None:
            return cached
        val = producer()
        if val is not None:
            Cache.set_json(key, val, ttl)
        return val

    @staticmethod
    def remember_text(key: str, ttl: int, producer: Callable[[], str]) -> str:
        cached = Cache.get_text(key)
        if cached is not None:
            return cached
        val = producer()
        if val is not None:
            Cache.set_text(key, val, ttl)
        return val
