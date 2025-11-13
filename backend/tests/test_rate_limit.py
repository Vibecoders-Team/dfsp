from __future__ import annotations

import time
from fastapi.testclient import TestClient

from app.main import app
from app.deps import rds

client = TestClient(app)


def _clear_rl_prefix(prefix: str) -> None:
    try:
        for k in list(rds.scan_iter(match=prefix + "*")):
            rds.delete(k)  # type: ignore[arg-type]
    except Exception:
        pass


def test_auth_login_rate_limit_per_endpoint():
    # Clear endpoint-specific rate-limit keys for this test window
    _clear_rl_prefix("rl:endpoint:auth_login:")

    # Perform 10 login attempts; the 11th should be 429 (limit 10/hour per IP)
    last_status = None
    got_429 = False
    for i in range(12):
        resp = client.post("/auth/login", json={})
        last_status = resp.status_code
        if last_status == 429:
            assert resp.headers.get("Retry-After") is not None
            got_429 = True
            break
    assert got_429, f"expected 429 on excessive login attempts, got last_status={last_status}"


def test_auth_register_rate_limit_per_endpoint():
    _clear_rl_prefix("rl:endpoint:auth_register:")

    # Perform 3 register attempts; the 4th should be 429 (limit 3/hour per IP)
    last_status = None
    got_429 = False
    for i in range(5):
        resp = client.post("/auth/register", json={})
        last_status = resp.status_code
        if last_status == 429:
            assert resp.headers.get("Retry-After") is not None
            got_429 = True
            break
    assert got_429, f"expected 429 on excessive register attempts, got last_status={last_status}"


def test_global_public_rate_limit_health_endpoint():
    # Clear per-IP minute window keys
    # We don't know exact IP, but testclient typically uses 127.0.0.1
    # Remove current/minute windows for safety
    win = int(time.time()) // 60
    prefix = f"rl:ip:127.0.0.1:{win}"
    _clear_rl_prefix(prefix)

    # Hit /health more than 100 times; expect at least one 429
    got_429 = False
    for i in range(120):
        r = client.get("/health")
        if r.status_code == 429:
            assert r.headers.get("Retry-After") is not None
            got_429 = True
            break
    assert got_429, "expected 429 for global per-IP rate limit on /health"

