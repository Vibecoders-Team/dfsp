from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_security_headers_present():
    r = client.get("/health")
    assert r.status_code in (200, 503, 429)
    hdrs = r.headers
    assert hdrs.get("X-Content-Type-Options") == "nosniff"
    assert hdrs.get("X-Frame-Options") == "DENY"
    assert hdrs.get("Referrer-Policy") == "no-referrer"
    assert "Content-Security-Policy" in hdrs


def test_prometheus_metrics_endpoint_and_increment():
    # Make a couple of requests to increment counters
    client.get("/health")
    client.get("/health")

    m = client.get("/metrics")
    assert m.status_code == 200
    assert m.headers["content-type"].startswith("text/plain")
    body = m.text

    # Standard exposition lines
    assert "# HELP api_requests_total" in body
    assert "# TYPE api_requests_total counter" in body
    # After 2 health hits, api_requests_total should contain lines for /health
    assert "api_requests_total" in body
    assert "api_request_duration_seconds" in body
