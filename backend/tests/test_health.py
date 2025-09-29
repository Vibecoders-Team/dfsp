from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# backend/tests/test_health.py
def test_healthz(client):
    r = client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_cors_parsing(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    s = Settings()
    assert s.cors_origins == ["http://a.com", "http://b.com"]

def test_quotas_nested(monkeypatch):
    from app.config import Settings
    monkeypatch.setenv("QUOTAS__META_TX_PER_DAY", "42")
    s = Settings()
    assert s.quotas.meta_tx_per_day == 42
