# backend/app/config.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List, Optional
from datetime import timedelta

from dotenv import load_dotenv
from pydantic import BaseModel, Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("dfsp.settings")

# --- .env автозагрузка из backend/.env (не мешает переменным окружения из compose) ---
env_path = Path(__file__).parent.parent / ".env"
if env_path.is_file():
    print(f"Loading environment variables from: {env_path}")
    load_dotenv(dotenv_path=env_path)
else:
    print(f"Warning: .env file not found at {env_path}")


# ------------------------------- вспомогательные вещи -------------------------------

class Quotas(BaseModel):
    download_bytes_day: int = 2_000_000_000  # 2 ГБ
    meta_tx_per_day: int = 50


def _parse_origins(val: str | List[str] | None) -> List[str]:
    """
    Принимает JSON-массив или CSV-строку и возвращает уникальный список, очищенный от пустых значений.
    """
    if val is None:
        return ["http://localhost:5173", "http://localhost:8000"]
    if isinstance(val, list):
        return [s.strip() for s in val if s and s.strip()]
    s = val.strip()
    if not s:
        return []
    try:
        arr = json.loads(s)
        if isinstance(arr, list):
            return [str(x).strip() for x in arr if str(x).strip()]
    except Exception:
        pass
    return [item.strip() for item in s.split(",") if item.strip()]


def _mask(s: str | None, keep: int = 4) -> str | None:
    if not s:
        return None
    return (s[:keep] + "…") if len(s) > keep else "…"


# ------------------------------- цепочка/контракты (опционально) -------------------------------

class ChainConfig(BaseModel):
    chainId: int
    verifyingContracts: dict[str, str]
    domain: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------- основные настройки ---------------------------------------

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # позволяем вложенные ключи через двойное подчёркивание: QUOTAS__META_TX_PER_DAY
        env_nested_delimiter="__",
    )

    # --- База/Redis ---
    postgres_dsn: str = Field(
        default="postgresql+psycopg://dfsp:dfsp@dfsp-db:5432/dfsp",
        alias="POSTGRES_DSN",
    )
    # поддерживаем и REDIS_URL, и REDIS_DSN — возьмём первый не-пустой
    redis_url_raw: Optional[str] = Field(default=None, alias="REDIS_URL")
    redis_dsn_raw: Optional[str] = Field(default=None, alias="REDIS_DSN")

    # --- Интеграции (пока могут быть None; подключим позже) ---
    ipfs_api: str | None = Field(default=None, alias="IPFS_API")
    rpc_url: str | None = Field(default=None, alias="RPC_URL")
    abi_dir: Path | None = Field(default=None, alias="ABI_DIR")
    chain_config_path: Path | None = Field(default=None, alias="CHAIN_CONFIG_PATH")

    # --- Anchoring/кванты ---
    anchor_period_min: PositiveInt = Field(default=60, alias="ANCHOR_PERIOD_MIN")

    # --- Security/JWT ---
    jwt_secret: str = Field("dev_secret", alias="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_access_ttl_minutes: PositiveInt = Field(15, alias="JWT_ACCESS_TTL_MINUTES")
    jwt_refresh_ttl_days: PositiveInt = Field(7, alias="JWT_REFRESH_TTL_DAYS")

    # --- Auth challenge ---
    auth_nonce_ttl: timedelta = Field(default=timedelta(minutes=5), alias="AUTH_NONCE_TTL")
    auth_nonce_bytes: PositiveInt = Field(default=16, alias="AUTH_NONCE_BYTES")

    # --- CORS ---
    cors_origins_raw: str | List[str] | None = Field(default=None, alias="CORS_ORIGINS")

    # --- Квоты (вложенные) ---
    quotas: Quotas = Field(default_factory=Quotas, alias="QUOTAS")

    CHAIN_RPC_URL: str

    DEPLOYMENT_JSON_PATH: str

    # ---------------------------- удобные производные/геттеры ----------------------------

    @property
    def cors_origins(self) -> list[str]:
        return _parse_origins(self.cors_origins_raw)

    @property
    def redis_dsn(self) -> str:
        """
        Единая точка для Redis DSN: сначала REDIS_URL, потом REDIS_DSN, иначе дефолт.
        """
        return self.redis_url_raw or self.redis_dsn_raw or "redis://dfsp-redis:6379/0"

    @property
    def jwt_access_ttl(self) -> timedelta:
        return timedelta(minutes=int(self.jwt_access_ttl_minutes))

    @property
    def jwt_refresh_ttl(self) -> timedelta:
        return timedelta(days=int(self.jwt_refresh_ttl_days))

    # --- Загрузка chain-config.json (опционально, без падений, если файла нет) ---
    def load_chain_config(self) -> ChainConfig | None:
        p = self.chain_config_path
        if not p:
            return None
        try:
            raw = json.loads(Path(p).read_text())
            # chainId может быть строкой
            if isinstance(raw.get("chainId"), str):
                raw["chainId"] = int(raw["chainId"])
            return ChainConfig(**raw)
        except FileNotFoundError:
            log.warning("Chain config not found at %s (ok for now)", p)
        except Exception as e:
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
            "quotas": self.quotas.model_dump(),
            "abi_dir": str(self.abi_dir) if self.abi_dir else None,
            "chain_config_path": str(self.chain_config_path) if self.chain_config_path else None,
            "chain_loaded": bool(chain),
            "chainId": getattr(chain, "chainId", None),
        }


# единый экземпляр
settings = Settings()
log.info("Loaded settings: %s", settings.debug_dump())

# На будущее (использовать по желанию):
# CHAIN = settings.load_chain_config()
