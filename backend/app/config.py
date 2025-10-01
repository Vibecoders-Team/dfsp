from __future__ import annotations

import json
import logging

from pathlib import Path
from typing import List, Any
from datetime import timedelta

from dotenv import load_dotenv

from pydantic import (
    BaseModel,
    Field,
    PositiveInt,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("dfsp.settings")

env_path = Path(__file__).parent.parent / ".env"
if env_path.is_file():
    print(f"Loading environment variables from: {env_path}")
    load_dotenv(dotenv_path=env_path)
else:
    print(f"Warning: .env file not found at {env_path}")

class Quotas(BaseModel):
    download_bytes_day: int = 2_000_000_000  # 2 ГБ
    meta_tx_per_day: int = 50


def _parse_origins(val: str | List[str] | None) -> List[str]:
    """
    Accept JSON array or comma-separated string. Returns a unique, trimmed list.
    """
    if val is None:
        return ["http://localhost:5173"]
    if isinstance(val, list):
        return [s.strip() for s in val if s and s.strip()]
    s = val.strip()
    if not s:
        return []
    # try JSON first
    try:
        arr = json.loads(s)
        if isinstance(arr, list):
            return [str(x).strip() for x in arr if str(x).strip()]
    except Exception:
        pass
    # fallback: CSV
    return [item.strip() for item in s.split(",") if item.strip()]


def _mask(s: str, keep: int = 4) -> str:
    return s[:keep] + "…" if len(s) > keep else "…"  # simple visual mask


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # КЛЮЧЕВОЕ: разрешаем вложенные env через двойное подчёркивание
        env_nested_delimiter="__",
    )

    postgres_dsn: str = Field(
        default="postgresql+asyncpg://test:test@db:5432/test",
        alias="POSTGRES_DSN",
    )
    redis_dsn: str | None = Field(default="redis://dfsp_redis:6379/0", alias="REDIS_DSN")
    ipfs_api: str | None = Field(default=None, alias="IPFS_API")
    rpc_url: str | None = Field(default=None, alias="RPC_URL")
    jwt_secret: str = Field(default="dev_secret", alias="JWT_SECRET")
    anchor_period_min: int = Field(default=60, alias="ANCHOR_PERIOD_MIN")

    # --- Security/JWT Settings (перенесено из settings.py) ---
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_access_ttl_minutes: int = Field(15, alias="JWT_ACCESS_TTL_MINUTES")
    jwt_refresh_ttl_days: int = Field(7, alias="JWT_REFRESH_TTL_DAYS")

    # --- Auth Challenge Settings (перенесено из settings.py) ---
    auth_nonce_ttl: timedelta = Field(timedelta(minutes=5), alias="AUTH_NONCE_TTL")
    auth_nonce_bytes: int = Field(16, alias="AUTH_NONCE_BYTES")

    # CORS как сырая строка и наш парсер (как уже сделали)
    cors_origins_raw: str | None = Field(default=None, alias="CORS_ORIGINS")
    def _parse_cors(self) -> list[str]:
        import json
        s = (self.cors_origins_raw or "").strip()
        if not s:
            return ["http://localhost:5173", "http://localhost:8000"]
        try:
            data = json.loads(s)
            if isinstance(data, list):
                return [str(x) for x in data]
        except Exception:
            pass
        if "," in s:
            return [x.strip() for x in s.split(",") if x.strip()]
        return [s]

    @property
    def cors_origins(self) -> list[str]:
        return self._parse_cors()

    # Вложенные квоты
    quotas: Quotas = Field(default_factory=Quotas, alias="QUOTAS")

    def debug_dump(self) -> dict:
        return {
            "postgres_dsn": "(hidden)" if self.postgres_dsn else None,
            "redis_dsn": self.redis_dsn,
            "ipfs_api": self.ipfs_api,
            "rpc_url": self.rpc_url,
            "anchor_period_min": self.anchor_period_min,
            "cors_origins": self.cors_origins,
            "quotas": self.quotas.model_dump(),
        }

settings = Settings()
log.info("Loaded settings: %s", settings.debug_dump())
