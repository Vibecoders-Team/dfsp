from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    postgres_dsn: str = "postgresql+psycopg://dfsp:dfsp@localhost:5432/dfsp"
    jwt_secret: str = "change_me"
    cors_origins: List[str] = ["http://localhost:5173"]

    class Config:
        env_file = ".env"

settings = Settings()
