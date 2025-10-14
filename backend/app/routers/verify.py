# app/routers/verify.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from web3 import Web3

from app.deps import get_db, get_chain
from app.models import File

router = APIRouter(prefix="/verify", tags=["verify"])


@router.get("/{file_id_hex}")
def verify(file_id_hex: str, db: Session = Depends(get_db), chain=Depends(get_chain)):
    # 1) Валидация id (ровно 32 байта в hex)
    if not (isinstance(file_id_hex, str) and file_id_hex.startswith("0x") and len(file_id_hex) == 66):
        raise HTTPException(400, "bad_file_id")

    fid = Web3.to_bytes(hexstr=file_id_hex)

    # 2) Off-chain из БД (не требуем авторизации)
    row = db.scalar(select(File).where(File.id == fid))
    off = {}
    if row:
        off = {
            "cid": row.cid,
            "checksum": row.checksum.hex() if isinstance(row.checksum, (bytes, bytearray)) else None,
            "size": int(row.size or 0),
            "mime": row.mime,
        }

    # 3) On-chain (безопасный путь: через cidOf/версии; НЕ зовём metaOf)
    on = {}
    try:
        cid = chain.cid_of(fid) or ""  # внутри уже есть fallback на разные ABI
        if cid:
            on["cid"] = cid
    except Exception:
        # Любая web3/ABI/адресная ошибка → считаем что on-chain пока пусто
        on = {}

    # 4) Сравнение (минимально — по cid)
    match = False
    if on and off:
        match = (on.get("cid") == off.get("cid"))

    return {"onchain": on, "offchain": off, "match": match}
