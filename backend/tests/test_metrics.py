from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_metrics_endpoint_and_request_counters():
    # Make a request to increment counters
    r1 = client.get("/health")
    assert r1.status_code in (200, 503)

    # Scrape metrics
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")

    body = r.text
    # Basic exposition format markers
    assert "# HELP api_requests_total" in body
    assert "# TYPE api_requests_total counter" in body
    assert "api_requests_total" in body

