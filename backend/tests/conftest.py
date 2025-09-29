# backend/tests/conftest.py
import os
import pytest
from fastapi.testclient import TestClient

# Минимальные env, чтобы Settings() собрался при импорте app.main
os.environ.setdefault("POSTGRES_DSN", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test_secret")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

@pytest.fixture(scope="session")
def client():
    from app.main import app  # импорт после выставления env
    return TestClient(app)
