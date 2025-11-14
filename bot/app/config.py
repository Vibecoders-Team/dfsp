from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str

    DFSP_API_URL: AnyHttpUrl
    DFSP_API_TOKEN: str | None = None

    QUEUE_DSN: str | None = None

    WEBHOOK_SECRET: str
    PUBLIC_WEB_ORIGIN: AnyHttpUrl

    PROM_PORT: int = 8001

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
