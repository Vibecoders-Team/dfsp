# backend/app/dependencies.py
from app.db.session import SessionLocal

def get_db():
    """FastAPI зависимость для получения сессии базы данных."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()