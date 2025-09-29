from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List

class Settings(BaseSettings):
    app_name: str = "DFSP API"
    cors_origins: List[str] = ["http://localhost:5173"]
    postgres_dsn: str = "postgresql+psycopg://dfsp:dfsp@localhost:5432/dfsp"
    jwt_secret: str = "change_me"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                return json.loads(v)
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    class Config:
        env_file = ".env"

settings = Settings()
