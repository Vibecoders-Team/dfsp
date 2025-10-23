from __future__ import annotations

from typing import Any, Dict, cast

from eth_typing import HexStr
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from web3 import Web3

from app.deps import get_db, get_chain
from app.models import File

router = APIRouter(prefix="/verify", tags=["verify"])


@router.get("/{file_id_hex}")
def verify(
        file_id_hex: str,
        db: Session = Depends(get_db),
        chain=Depends(get_chain),
):
    # manual validation to produce 400 instead of 422
    if not (isinstance(file_id_hex, str) and file_id_hex.startswith("0x") and len(file_id_hex) == 66):
        raise HTTPException(400, "bad_file_id")
    fid = Web3.to_bytes(hexstr=cast(HexStr, file_id_hex))

    row = db.scalar(select(File).where(File.id == fid))
    off: Dict[str, Any] = {}
    if row:
        off = {
            "cid": row.cid,
            "checksum": row.checksum.hex() if isinstance(row.checksum, (bytes, bytearray)) else None,
            "size": int(row.size or 0),
            "mime": row.mime,
        }

    on: Dict[str, Any] = {}
    try:
        cid = chain.cid_of(fid) or ""
        if cid:
            on["cid"] = cid
    except Exception:
        on = {}

    match = bool(on) and bool(off) and (on.get("cid") == off.get("cid"))

    return {"onchain": on, "offchain": off, "match": match}
