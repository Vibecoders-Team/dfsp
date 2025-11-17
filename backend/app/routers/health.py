from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import get_chain, get_db, rds

router = APIRouter(tags=["health"])
START_TIME = time.time()


def _ok(v: object) -> bool:
    try:
        return (isinstance(v, dict) and bool(v.get("ok"))) or v == "ok"
    except Exception:
        return False


def _parse_required(env_val: str | None) -> list[str]:
    if not env_val:
        return ["db", "redis"]
    items = [x.strip() for x in env_val.split(",") if x.strip()]
    return items or ["db", "redis"]


def get_health_checks(db: Session) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    # db
    try:
        db.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = {"error": str(e)}

    # redis
    try:
        rds.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = {"error": str(e)}

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

        if chain_ok:
            checks["chain"] = {"ok": True, "chainId": chain_id}
        else:
            checks["chain"] = {"error": "Not connected"}
        if names:
            checks["contracts"] = {"ok": True, "names": names}
        else:
            checks["contracts"] = {"error": "Not loaded"}

    except Exception as e:
        checks["chain"] = {"error": str(e)}
        checks["contracts"] = {"error": str(e)}

    # ipfs (API)
    try:
        base = os.getenv("IPFS_API_URL", "http://ipfs:5001/api/v0").rstrip("/")
        req = urllib.request.Request(base + "/id", data=b"", method="POST")  # type: ignore[arg-type]
        with urllib.request.urlopen(req, timeout=3) as resp:
            j = json.loads(resp.read().decode())
        checks["ipfs"] = {"ok": True, "id": j.get("ID")}
    except Exception as e:
        checks["ipfs"] = {"error": str(e)}

    return checks


@router.get("/health", status_code=status.HTTP_200_OK)
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    checks = get_health_checks(db)
    is_healthy = all(_ok(v) for v in checks.values())
    status_str = "healthy" if is_healthy else "degraded"
    return {
        "status": status_str,
        "version": os.getenv("GIT_SHA") or "dev",
        "uptime": time.time() - START_TIME,
        "checks": checks,
    }


@router.get("/live", status_code=status.HTTP_200_OK)
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def ready(db: Session = Depends(get_db), response: Response = Response()) -> dict[str, Any]:
    checks = get_health_checks(db)
    required = _parse_required(os.getenv("READINESS_REQUIRED"))  # default: ["db", "redis"]
    is_ready = all(_ok(checks.get(k)) for k in required)

    if is_ready:
        return {"status": "ready", "required": required}
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "required": required, "checks": checks}
