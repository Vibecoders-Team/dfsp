from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("dfsp.settings")

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
    Поддерживает '*' (любой источник).
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
            # Не валидный JSON — пробуем CSV-разделитель
            out = [item.strip() for item in s.split(",") if item.strip()]

    # убираем дубликаты, сохраняя порядок
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
    cors_origin_raw: str | None = Field(default=None, alias="CORS_ORIGIN")

    # --- Квоты (вложенные, дефолты) ---
    quotas: Quotas = Field(default_factory=Quotas, alias="QUOTAS")
    # Плоские env-переменные для квот (удобные для DevOps)
    quota_download_bytes_day_env: Optional[int] = Field(default=None, alias="QUOTA_DOWNLOAD_BYTES_PER_DAY")
    quota_meta_tx_per_day_env: Optional[int] = Field(default=None, alias="QUOTA_META_TX_PER_DAY")

    # --- Relayer/Celery очереди ---
    relayer_high_queue: str = Field(default="relayer.high", alias="RELAYER_HIGH_QUEUE")
    relayer_default_queue: str = Field(default="relayer.default", alias="RELAYER_DEFAULT_QUEUE")

    # --- Proof-of-Work параметры (резерв под будущую фичу) ---
    pow_difficulty_base: int = Field(default=18, alias="POW_DIFFICULTY_BASE")

    chain_rpc_url_raw: str | None = Field(default=None, alias="CHAIN_RPC_URL")

    def __init__(
            self,
            jwt_secret: str = "dev_secret",
            jwt_algorithm: str = "HS256",
            jwt_access_ttl_minutes: int = 15,
            jwt_refresh_ttl_days: int = 7,
            chain_rpc_url_raw: str | None = None,
            **values: Any,
    ) -> None:
        """
        Поддерживаем явный конструктор только ради статического анализатора:
        - значения по-умолчанию синхронизированы с Field(...) в классе;
        - остальные значения (из env/kwargs) попадут в super().__init__ как обычно.
        """
        # если кто-то передал явно в kwargs — не перезаписываем
        values.setdefault("jwt_secret", jwt_secret)
        values.setdefault("jwt_algorithm", jwt_algorithm)
        values.setdefault("jwt_access_ttl_minutes", jwt_access_ttl_minutes)
        values.setdefault("jwt_refresh_ttl_days", jwt_refresh_ttl_days)
        # Для CHAIN_RPC_URL поле у тебя было ALL-CAPS — используем именно такое имя
        values.setdefault("CHAIN_RPC_URL", chain_rpc_url_raw)
        super().__init__(**values)

    # ---------------------------- удобные производные/геттеры ----------------------------
    @property
    def chain_rpc_url(self) -> str:
        """Возвращает CHAIN_RPC_URL или бросает ошибку — явная и ранняя ошибка конфигурации."""
        val = self.chain_rpc_url_raw
        if not val:
            raise RuntimeError("Missing required configuration: CHAIN_RPC_URL (set env CHAIN_RPC_URL)")
        return val

    @property
    def cors_origins(self) -> list[str]:
        """
        Итоговый список Origin'ов для CORS.
        Приоритет: CORS_ORIGINS (если задан) -> CORS_ORIGIN (если задан) -> дефолт.
        Спец-случай '*': вернём ['*'].
        """
        if self.cors_origins_raw not in (None, "", []):
            return _parse_origins(self.cors_origins_raw)
        if self.cors_origin_raw not in (None, ""):
            return _parse_origins(self.cors_origin_raw)
        return _parse_origins(None)

    @property
    def cors_origin(self) -> str | None:
        """
        Возвращает первый origin из cors_origins (или None, если не задан).
        Удобно, если нужен один «основной» origin, например для генерации URL.
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
        Единая точка для Redis DSN: сначала REDIS_URL, потом REDIS_DSN, иначе дефолт.
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
        """Возвращает квоты с учётом плоских env-переменных (если заданы)."""
        q = Quotas(**self.quotas.model_dump()) if isinstance(self.quotas, Quotas) else Quotas()
        if self.quota_download_bytes_day_env is not None:
            q.download_bytes_day = int(self.quota_download_bytes_day_env)
        if self.quota_meta_tx_per_day_env is not None:
            q.meta_tx_per_day = int(self.quota_meta_tx_per_day_env)
        return q

    # --- Загрузка chain-config.json (опционально, без падений, если файла нет) ---
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
            # JSON парсинг, приведение типов или валидация ChainConfig
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
        }


# единый экземпляр
settings = Settings()
log.info("Loaded settings: %s", settings.debug_dump())

# На будущее (использовать по желанию):
# CHAIN = settings.load_chain_config()
