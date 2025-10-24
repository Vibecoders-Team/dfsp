import json
import math
import os
import urllib.request
import urllib.request
from typing import Any, cast

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import get_db, rds, get_chain

router = APIRouter(prefix="/health", tags=["health"])


def _ok(res, err=None, **extra):
    d = {"ok": res}
    if err:
        d["error"] = str(err)
    d.update(extra)
    return d


def _parse_int(val) -> int:
    try:
        if val is None:
            return 0
        if isinstance(val, bytes):
            val = val.decode()
        return int(val)
    except Exception:
        return 0


def _percentile_vals(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    data = sorted(values)
    k = (len(data) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(data[int(k)])
    return float(data[f] * (c - k) + data[c] * (k - f))


@router.get("")
def health(db: Session = Depends(get_db)):
    out = {"ok": True, "api": _ok(True, version=os.getenv("GIT_SHA") or "dev")}

    # db
    try:
        db.execute(text("SELECT 1"))
        out["db"] = _ok(True)
    except Exception as e:
        out["db"] = _ok(False, e)
        out["ok"] = False

    # redis
    try:
        pong = rds.ping()
        out["redis"] = _ok(bool(pong))
        if not pong:
            out["ok"] = False
    except Exception as e:
        out["redis"] = _ok(False, e)
        out["ok"] = False

    # chain + contracts
    try:
        chain = get_chain()
        if not chain.contracts:
            chain.reload_contracts()
        names = list(chain.contracts.keys())
        # Robust chain OK: if we can read chain_id or is_connected is True
        try:
            chain_id = int(chain.w3.eth.chain_id)
            chain_ok = True
        except Exception:
            chain_id = None
            try:
                chain_ok = bool(chain.w3.is_connected())
            except Exception:
                chain_ok = False
        out["chain"] = _ok(chain_ok, chainId=chain_id)
        out["contracts"] = _ok(bool(names), names=names)
        if not names:
            out["ok"] = False
    except Exception as e:
        out["chain"] = _ok(False, e)
        out["contracts"] = _ok(False, e)
        out["ok"] = False

    # ipfs (API)
    try:
        base = os.getenv("IPFS_API_URL", "http://ipfs:5001/api/v0").rstrip("/")
        req = urllib.request.Request(base + "/id", data=b"", method="POST")  # type: ignore[arg-type]
        with urllib.request.urlopen(req, timeout=3) as resp:
            j = json.loads(resp.read().decode())
        out["ipfs"] = _ok(True, id=j.get("ID"))
    except Exception as e:
        out["ipfs"] = _ok(False, e)
        out["ok"] = False

    # relayer metrics
    try:
        high_q = os.getenv("RELAYER_HIGH_QUEUE", "relayer.high")
        def_q = os.getenv("RELAYER_DEFAULT_QUEUE", "relayer.default")
        q_high_len = _parse_int(rds.llen(high_q)) if hasattr(rds, "llen") else 0
        q_def_len = _parse_int(rds.llen(def_q)) if hasattr(rds, "llen") else 0
        success_total = _parse_int(rds.get("metrics:relayer:success_total"))
        error_total = _parse_int(rds.get("metrics:relayer:error_total"))
        enq_high = _parse_int(rds.get(f"metrics:relayer:enqueue_total:{high_q}"))
        enq_def = _parse_int(rds.get(f"metrics:relayer:enqueue_total:{def_q}"))
        raw = rds.lrange("metrics:relayer:durations:submit_forward", 0, 199) or []
        durs_list: list[Any] = list(raw) if isinstance(raw, list) else []
        vals_f: list[float] = []
        for x in durs_list:
            try:
                if isinstance(x, bytes):
                    x = x.decode()
                vals_f.append(float(x))
            except Exception:
                continue
        p50 = _percentile_vals(vals_f, 0.5)
        p95 = _percentile_vals(vals_f, 0.95)
        out["relayer"] = _ok(True,
                              queues={high_q: q_high_len, def_q: q_def_len},
                              metrics={
                                  "success_total": success_total,
                                  "error_total": error_total,
                                  "enqueue": {high_q: enq_high, def_q: enq_def},
                                  "p50_ms": p50,
                                  "p95_ms": p95,
                              })
    except Exception as e:
        out["relayer"] = _ok(False, e)
        out["ok"] = False

    return out
