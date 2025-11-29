from __future__ import annotations

import json
import os
import urllib.parse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from redis.exceptions import ResponseError

from app.deps import get_ipfs, rds

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


def _build_content_disposition(filename: str | None) -> str:
    if not filename:
        return "attachment"
    ascii_name = filename.encode("ascii", "ignore").decode() or "download"
    quoted = urllib.parse.quote(filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"


@router.get("/one-time/{token}", response_model=None)
def consume_one_time(
    token: str,
    request: Request,
) -> RedirectResponse | dict[str, object] | StreamingResponse:
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

    # Binary fetch: consume token and stream from IPFS with Content-Disposition
    if "application/octet-stream" in accept or "attachment" in accept:
        raw = _getdel(key)
        if not raw:
            raise HTTPException(status_code=410, detail="expired")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
        ipfs_path = str(payload.get("ipfsPath") or "")
        filename = payload.get("fileName") or "download"
        if not ipfs_path.startswith("/ipfs/"):
            raise HTTPException(status_code=400, detail="bad_ipfs_path")
        cid = ipfs_path.split("/ipfs/")[1]

        ipfs = get_ipfs()
        try:
            data = ipfs.cat(cid)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"ipfs_error:{e}") from e

        headers = {"Content-Disposition": _build_content_disposition(filename)}
        media_type = "application/octet-stream"
        return StreamingResponse(iter([data]), media_type=media_type, headers=headers)

    # Browser navigation: do not consume, just redirect to frontend page
    if not rds.exists(key):
        raise HTTPException(status_code=410, detail="expired")

    dest = f"{PUBLIC_WEB_ORIGIN}/dl/one-time/{token}"
    return RedirectResponse(url=dest, status_code=302)
