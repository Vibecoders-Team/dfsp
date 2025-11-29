from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from redis.exceptions import ResponseError

from app.deps import rds

PUBLIC_WEB_ORIGIN = os.getenv("PUBLIC_WEB_ORIGIN", "http://localhost:3000").rstrip("/")
DL_ONCE_TTL = int(os.getenv("DL_ONCE_TTL", "300"))

router = APIRouter(prefix="/dl", tags=["download"])


def _getdel(key: str) -> str | None:
    try:
        raw = rds.execute_command("GETDEL", key)
    except ResponseError:
        raw = rds.get(key)
        if raw is not None:
            rds.delete(key)
    if not raw:
        return None
    if isinstance(raw, (bytes, bytearray)):
        return raw.decode()
    return str(raw)


@router.get("/one-time/{token}", response_model=None)
def consume_one_time(
    token: str,
    request: Request,
) -> RedirectResponse | dict[str, object]:
    key = f"dl:once:{token}"
    accept = request.headers.get("accept", "")

    # JSON fetch consumes the token
    if "application/json" in accept:
        raw = _getdel(key)
        if not raw:
            raise HTTPException(status_code=410, detail="expired")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
        return payload

    # Browser navigation: do not consume, just redirect to frontend page
    if not rds.exists(key):
        raise HTTPException(status_code=410, detail="expired")

    dest = f"{PUBLIC_WEB_ORIGIN}/dl/one-time/{token}"
    return RedirectResponse(url=dest, status_code=302)
