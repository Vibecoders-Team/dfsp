from typing import Literal

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str

    DFSP_API_URL: AnyHttpUrl
    DFSP_API_TOKEN: str | None = None

    QUEUE_DSN: str | None = None
    REDIS_DSN: str = "redis://localhost:6379/0"
    NOTIFY_STREAM_KEY: str = "tg.notifications"
    NOTIFY_CONSUMER_GROUP: str = "tg-bot"
    NOTIFY_COALESCE_WINDOW_SEC: int = 60
    NOTIFY_DAILY_MAX: int = 500
    NOTIFY_DEFAULT_SUBSCRIBED: bool = True

    WEBHOOK_SECRET: str
    PUBLIC_WEB_ORIGIN: AnyHttpUrl

    PROM_PORT: int = 8001
    BOT_DB_DSN: str = "postgresql://dfsp_bot:dfsp_bot@localhost:5432/dfsp_bot"
    BOT_DEFAULT_LANGUAGE: str = "ru"
    I18N_FALLBACK: str = "ru"
    CALLBACK_HMAC_SECRET: str | None = None

    # новый конфиг
    BOT_MODE: Literal["dev", "prod"] = "dev"  # dev = polling, prod = webhook
    APP_HOST: str = "0.0.0.0"  # noqa: S104
    APP_PORT: int = 8080

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
