import json
import os
import urllib.request
import urllib.request

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import get_db, rds, get_chain

router = APIRouter(prefix="/health", tags=["health"])


def _ok(res, err=None, **extra):
    d = {"ok": res}
    if err: d["error"] = str(err)
    d.update(extra)
    return d


@router.get("")
def health(db: Session = Depends(get_db)):
    out = {"ok": True, "api": _ok(True, version=os.getenv("GIT_SHA") or "dev")}

    # api

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
        if not pong: out["ok"] = False
    except Exception as e:
        out["redis"] = _ok(False, e)
        out["ok"] = False

    # chain + contracts
    try:
        chain = get_chain()
        if not chain.contracts:
            chain.reload_contracts()
        names = list(chain.contracts.keys())
        out["chain"] = _ok(chain.w3.is_connected(),
                           chainId=(chain.w3.eth.chain_id if chain.w3.is_connected() else None))
        out["contracts"] = _ok(bool(names), names=names)
        if not names: out["ok"] = False
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

    return out
