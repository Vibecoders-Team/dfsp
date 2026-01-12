from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field, PositiveInt, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("dfsp.settings")

env_path = Path(__file__).parent.parent / ".env"
if env_path.is_file():
    log.info("Loading environment variables from: %s", env_path)
    load_dotenv(dotenv_path=env_path)
else:
    log.warning("Warning: .env file not found at %s", env_path)


# ------------------------------- helpers -------------------------------


class Quotas(BaseModel):
    download_bytes_day: int = 2_000_000_000  # 2 GB
    meta_tx_per_day: int = 50


def _parse_origins(val: str | list[str] | None) -> list[str]:
    """
    Accept JSON array or CSV string and return a unique list with empty values removed.
    Supports '*' (any origin).
    """
    if val is None:
        return ["http://localhost:5173", "http://localhost:8000"]
    if isinstance(val, list):
        out = [s.strip() for s in val if s and s.strip()]
    else:
        s = val.strip()
        if not s:
            return []
        if s == "*":
            return ["*"]
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                out = [str(x).strip() for x in arr if str(x).strip()]
            else:
                out = [s]
        except json.JSONDecodeError:
            # Invalid JSON - try CSV separator
            out = [item.strip() for item in s.split(",") if item.strip()]

    # remove duplicates while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for o in out:
        if o not in seen:
            seen.add(o)
            uniq.append(o)
    return uniq


def _mask(s: str | None, keep: int = 4) -> str | None:
    if not s:
        return None
    return (s[:keep] + "…") if len(s) > keep else "…"


# ------------------------------- chain/contracts (optional) -------------------------------


class ChainConfig(BaseModel):
    chainId: int
    verifyingContracts: dict[str, str]
    domain: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------- core settings ---------------------------------------


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    # --- Database/Redis ---
    postgres_dsn: str = Field(alias="POSTGRES_DSN")
    # support both REDIS_URL and REDIS_DSN - take the first non-empty
    redis_url_raw: str | None = Field(default=None, alias="REDIS_URL")
    redis_dsn_raw: str | None = Field(default=None, alias="REDIS_DSN")

    # --- Integrations (can be None for now; we'll connect them later) ---
    ipfs_api: str | None = Field(default=None, alias="IPFS_API")
    rpc_url: str | None = Field(default=None, alias="RPC_URL")
    abi_dir: Path | None = Field(default=None, alias="ABI_DIR")
    chain_config_path: Path | None = Field(default=None, alias="CHAIN_CONFIG_PATH")

    # --- Anchoring/periods ---
    anchor_period_min: PositiveInt = Field(default=60, alias="ANCHOR_PERIOD_MIN")

    # --- Security/JWT ---
    jwt_secret: str = Field("dev_secret", alias="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_access_ttl_minutes: int = Field(default=30, alias="JWT_ACCESS_TTL_MINUTES")
    jwt_refresh_ttl_days: PositiveInt = Field(default=7, alias="JWT_REFRESH_TTL_DAYS")
    jwt_leeway_seconds: int = Field(default=600, alias="JWT_LEEWAY_SECONDS")

    # --- Auth challenge ---
    auth_nonce_ttl: timedelta | int = Field(default=timedelta(minutes=5), alias="AUTH_NONCE_TTL")
    auth_nonce_bytes: PositiveInt = Field(default=16, alias="AUTH_NONCE_BYTES")

    @field_validator("auth_nonce_ttl", mode="before")
    @classmethod
    def parse_auth_nonce_ttl(cls, v: object) -> object:
        if isinstance(v, int):
            return timedelta(seconds=v)
        return v

    # --- CORS ---
    cors_origins_raw: str | list[str] | None = Field(default=None, alias="CORS_ORIGINS")
    cors_origin_raw: str | None = Field(default=None, alias="CORS_ORIGIN")

    # --- Quotas (nested, defaults) ---
    quotas: Quotas = Field(default_factory=Quotas, alias="QUOTAS")
    # Flat env vars for quotas (convenient for DevOps)
    quota_download_bytes_day_env: int | None = Field(default=None, alias="QUOTA_DOWNLOAD_BYTES_PER_DAY")
    quota_meta_tx_per_day_env: int | None = Field(default=None, alias="QUOTA_META_TX_PER_DAY")

    # --- Relayer/Celery queues ---
    relayer_high_queue: str = Field(default="relayer.high", alias="RELAYER_HIGH_QUEUE")
    relayer_default_queue: str = Field(default="relayer.default", alias="RELAYER_DEFAULT_QUEUE")

    # --- Proof-of-Work parameters ---
    pow_difficulty_base: int = Field(default=18, alias="POW_DIFFICULTY_BASE")
    pow_challenge_ttl_seconds: int = Field(default=300, alias="POW_CHALLENGE_TTL_SECONDS")  # 5 minutes
    pow_enabled: bool = Field(default=True, alias="POW_ENABLED")  # global switch

    chain_rpc_url_raw: str | None = Field(default=None, alias="CHAIN_RPC_URL")
    chain_public_rpc_url: str = os.getenv("CHAIN_PUBLIC_RPC_URL", "")

    # --- NEW: pooling options ---
    postgres_pool_size: int = Field(default=20, alias="POSTGRES_POOL_SIZE")
    postgres_max_overflow: int = Field(default=10, alias="POSTGRES_MAX_OVERFLOW")
    redis_max_connections: int = Field(default=100, alias="REDIS_MAX_CONNECTIONS")

    # --- NEW: relayer signing (optional) ---
    chain_tx_from: str | None = Field(default=None, alias="CHAIN_TX_FROM")
    relayer_private_key: str | None = Field(default=None, alias="RELAYER_PRIVATE_KEY")

    def __init__(
        self,
        jwt_secret: str | None = None,
        jwt_algorithm: str = "HS256",
        jwt_access_ttl_minutes: int = 15,
        jwt_refresh_ttl_days: int = 7,
        chain_rpc_url_raw: str | None = None,
        **values: Any,  # noqa: ANN401 - forwarded kwargs to BaseSettings are intentionally untyped
    ) -> None:
        """
        Explicit constructor is only for static analyzers:
        - default values are synced with Field(...) in the class;
        - other values (from env/kwargs) still go to super().__init__ as usual.
        """
        # if passed explicitly in kwargs - do not overwrite
        values.setdefault("jwt_secret", jwt_secret or "dev_secret")
        values.setdefault("jwt_algorithm", jwt_algorithm)
        values.setdefault("jwt_access_ttl_minutes", jwt_access_ttl_minutes)
        values.setdefault("jwt_refresh_ttl_days", jwt_refresh_ttl_days)
        # CHAIN_RPC_URL is ALL-CAPS - use that exact name
        values.setdefault("CHAIN_RPC_URL", chain_rpc_url_raw)
        super().__init__(**values)

    # ---------------------------- convenience derived values/getters ----------------------------
    @property
    def chain_rpc_url(self) -> str:
        """Return CHAIN_RPC_URL or raise an explicit early config error."""
        val = self.chain_rpc_url_raw
        if not val:
            raise RuntimeError("Missing required configuration: CHAIN_RPC_URL (set env CHAIN_RPC_URL)")
        return val

    @property
    def cors_origins(self) -> list[str]:
        """
        Final list of Origins for CORS.
        Priority: CORS_ORIGINS (if set) -> CORS_ORIGIN (if set) -> default.
        Special case '*': return ['*'].
        """
        if self.cors_origins_raw not in (None, "", []):
            return _parse_origins(self.cors_origins_raw)
        if self.cors_origin_raw not in (None, ""):
            return _parse_origins(self.cors_origin_raw)
        return _parse_origins(None)

    @property
    def cors_origin(self) -> str | None:
        """
        Return the first origin from cors_origins (or None if not set).
        Useful when a single "primary" origin is needed, e.g. for URL generation.
        """
        origins: list[str] = self.cors_origins
        if not origins:
            return None
        if origins == ["*"]:
            return "*"
        return origins[0]

    @property
    def redis_dsn(self) -> str:
        """
        Single source for Redis DSN: REDIS_URL first, then REDIS_DSN, otherwise default.
        """
        return self.redis_url_raw or self.redis_dsn_raw or "redis://dfsp-redis:6379/0"

    @property
    def jwt_access_ttl(self) -> timedelta:
        return timedelta(minutes=int(self.jwt_access_ttl_minutes))

    @property
    def jwt_refresh_ttl(self) -> timedelta:
        return timedelta(days=int(self.jwt_refresh_ttl_days))

    @property
    def quotas_effective(self) -> Quotas:
        """Return quotas with flat env overrides applied (if set)."""
        q = Quotas(**self.quotas.model_dump()) if isinstance(self.quotas, Quotas) else Quotas()
        if self.quota_download_bytes_day_env is not None:
            q.download_bytes_day = int(self.quota_download_bytes_day_env)
        if self.quota_meta_tx_per_day_env is not None:
            q.meta_tx_per_day = int(self.quota_meta_tx_per_day_env)
        return q

    # --- Load chain-config.json (optional, no failure if missing) ---
    def load_chain_config(self) -> ChainConfig | None:
        p = self.chain_config_path
        if not p:
            return None
        try:
            raw_text = Path(p).read_text()
            raw = json.loads(raw_text)
            if isinstance(raw.get("chainId"), str):
                raw["chainId"] = int(raw["chainId"])
            return ChainConfig(**raw)
        except FileNotFoundError:
            log.warning("Chain config not found at %s (ok for now)", p)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            # JSON parsing, type coercion, or ChainConfig validation
            log.warning("Failed to load chain config from %s: %s", p, e)
        return None

    def debug_dump(self) -> dict[str, Any]:
        chain = self.load_chain_config()
        return {
            "postgres_dsn": _mask(self.postgres_dsn, 16),
            "redis_dsn": _mask(self.redis_dsn, 16),
            "ipfs_api": self.ipfs_api,
            "rpc_url": self.rpc_url,
            "anchor_period_min": self.anchor_period_min,
            "cors_origins": self.cors_origins,
            "quotas": self.quotas_effective.model_dump(),
            "abi_dir": str(self.abi_dir) if self.abi_dir else None,
            "chain_config_path": str(self.chain_config_path) if self.chain_config_path else None,
            "relayer_queues": {
                "high": self.relayer_high_queue,
                "default": self.relayer_default_queue,
            },
            "pow": {"difficulty_base": self.pow_difficulty_base},
            "chain_loaded": bool(chain),
            "chainId": getattr(chain, "chainId", None),
            "chain_tx_from": self.chain_tx_from,
            "relayer_pk": _mask(self.relayer_private_key, 10),
        }


# single instance
settings = Settings()
log.info("Loaded settings: %s", settings.debug_dump())

# For future use (optional):
# CHAIN = settings.load_chain_config()
