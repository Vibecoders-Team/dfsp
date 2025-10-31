from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from fastapi.testclient import TestClient

from app.main import app
import app.deps as deps
import app.telemetry.metrics as metrics_mod
import app.routers.health as health_mod


class _Pipe:
    def __init__(self, rds: "FakeRedis"):
        self._ops: List[tuple[str, tuple[Any, ...]]] = []
        self._rds = rds

    def incr(self, key: str):
        self._ops.append(("incr", (key,)))
        return self

    def incrby(self, key: str, val: int):
        self._ops.append(("incrby", (key, val)))
        return self

    def expire(self, key: str, _):
        # TTL ignored in fake
        self._ops.append(("expire", (key, 0)))
        return self

    def execute(self):
        for op, args in self._ops:
            if op == "incr":
                self._rds.incr(args[0])
            elif op == "incrby":
                self._rds.incrby(args[0], int(args[1]))
        self._ops.clear()
        return True


class FakeRedis:
    def __init__(self):
        self.kv: Dict[str, Any] = {}
        self.lists: Dict[str, List[Any]] = {}

    def ping(self):
        return True

    def get(self, key: str):
        return self.kv.get(key)

    def set(self, key: str, val: Any, ex: Optional[int] = None):
        self.kv[key] = val
        return True

    def setex(self, key: str, ex: int, val: Any):
        self.kv[key] = val
        return True

    def delete(self, key: str):
        return 1 if self.kv.pop(key, None) is not None else 0

    def incr(self, key: str):
        v = int(self.kv.get(key) or 0)
        self.kv[key] = str(v + 1)
        return int(self.kv[key])

    def incrby(self, key: str, by: int):
        v = int(self.kv.get(key) or 0)
        self.kv[key] = str(v + int(by))
        return int(self.kv[key])

    def llen(self, key: str):
        return len(self.lists.get(key, []))

    def lrange(self, key: str, start: int, stop: int):
        arr = self.lists.get(key, [])
        if stop < 0:
            stop = len(arr) + stop
        return arr[start: stop + 1]

    def lpush(self, key: str, val: Any):
        self.lists.setdefault(key, []).insert(0, val)
        return len(self.lists[key])

    def ltrim(self, key: str, start: int, stop: int):
        arr = self.lists.get(key, [])
        self.lists[key] = arr[start: stop + 1]
        return True

    def scan_iter(self, match: str) -> Iterable[bytes]:
        # very basic glob-like prefix matching for tests
        prefix = match.rstrip("*")
        for k in list(self.kv.keys()):
            if k.startswith(prefix):
                yield k.encode("utf-8")

    def pipeline(self):
        return _Pipe(self)


def setup_fake_redis() -> FakeRedis:
    r = FakeRedis()
    # Relayer metrics
    r.kv["metrics:relayer:success_total"] = "3"
    r.kv["metrics:relayer:error_total"] = "1"
    r.kv["metrics:relayer:enqueue_total:relayer.high"] = "2"
    r.kv["metrics:relayer:enqueue_total:relayer.default"] = "5"
    r.lists["metrics:relayer:durations:submit_forward"] = ["100", "200", "400"]  # ms

    # PoW / quotas
    r.kv["metrics:pow_challenges_total"] = "5"
    r.kv["metrics:pow_verifications_total:ok"] = "4"
    r.kv["metrics:pow_quota_rejections:pow_token_missing"] = "2"
    r.kv["metrics:pow_quota_rejections:download_quota"] = "1"
    r.kv["metrics:pow_quota_rejections:meta_tx_quota"] = "1"

    # Queues
    r.lists["relayer.high"] = []
    r.lists["relayer.default"] = [1, 2]

    return r


def override_db():
    class _Res:
        def __init__(self, val: int):
            self._val = val
        def scalar(self):
            return self._val
    class _DB:
        def execute(self, stmt):
            q = str(stmt)
            if "from users" in q:
                return _Res(0)
            if "from grants" in q:
                return _Res(0)
            return _Res(1)
    def _gen():
        yield _DB()
    return _gen


def test_metrics_prometheus_and_health_ok(monkeypatch):
    # Patch Redis everywhere it's referenced
    fake = setup_fake_redis()
    deps.rds = fake
    metrics_mod.rds = fake
    health_mod.rds = fake

    # Override DB dependency
    app.dependency_overrides[deps.get_db] = override_db()

    client = TestClient(app)

    # Call /metrics (also triggers middleware counters)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    # Check several key metrics are present
    assert "pow_challenges_total" in body
    assert "meta_tx_total" in body
    assert "relayer_queue_length" in body

    # Call /health
    hresp = client.get("/health")
    assert hresp.status_code == 200
    j = hresp.json()
    assert isinstance(j, dict)
    assert j.get("relayer")
    assert j.get("ok") in (True, False)

