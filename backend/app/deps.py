from .config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import redis
from .config import settings

def get_settings():
    return settings


engine = create_engine(settings.postgres_dsn, future=True)
SessionLocal = sessionmaker(engine, autoflush=False, autocommit=False, future=True)

rds = redis.from_url(settings.redis_dsn, decode_responses=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()