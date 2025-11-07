from __future__ import annotations

import json
from typing import Any, Callable, Optional


class Cache:
    @staticmethod
    def _rds():
        try:
            # Lazy import to avoid circular dependency during app startup
            from app.deps import rds as _rds  # type: ignore
            return _rds
        except Exception:
            # Fallback: construct a temporary client from env if deps is not ready
            import os
            import redis  # type: ignore
            url = os.getenv("REDIS_URL") or os.getenv("REDIS_DSN") or "redis://localhost:6379/0"
            return redis.from_url(url, decode_responses=True)

    @staticmethod
    def get_text(key: str) -> Optional[str]:
        try:
            val = Cache._rds().get(key)
            if val is None:
                return None
            if isinstance(val, (bytes, bytearray)):
                return val.decode("utf-8", errors="ignore")
            return str(val)
        except Exception:
            return None

    @staticmethod
    def set_text(key: str, value: str, ttl: int) -> None:
        try:
            Cache._rds().setex(key, int(ttl), value)
        except Exception:
            pass

    @staticmethod
    def get_json(key: str) -> Optional[Any]:
        txt = Cache.get_text(key)
        if not txt:
            return None
        try:
            return json.loads(txt)
        except Exception:
            return None

    @staticmethod
    def set_json(key: str, value: Any, ttl: int) -> None:
        try:
            Cache.set_text(key, json.dumps(value, separators=(",", ":")), ttl)
        except Exception:
            pass

    @staticmethod
    def delete(key: str) -> None:
        try:
            Cache._rds().delete(key)
        except Exception:
            pass

    @staticmethod
    def remember_json(key: str, ttl: int, producer: Callable[[], Any]) -> Any:
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
