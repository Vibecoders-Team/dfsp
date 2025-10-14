from __future__ import annotations

import hashlib
from typing import Literal

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from web3 import Web3

from app.blockchain.web3_client import Chain
from app.deps import get_chain, get_ipfs
from app.ipfs.client import IpfsClient
from app.models import User
from app.security import get_current_user  # guard

router = APIRouter(prefix="/storage", tags=["storage"])


class StoreOut(BaseModel):
    id_hex: str
    cid: str
    tx_hash: str
    url: str


@router.post("/store", response_model=StoreOut)
async def store_file(
        file: UploadFile = File(...),
        # опционально фиксируем id (bytes32, hex) — чтобы заюзать updateCid
        id_hex: str | None = Form(None),
        chain: Chain = Depends(get_chain),
        ipfs: IpfsClient = Depends(get_ipfs),
        user: User = Depends(get_current_user),
):
    MAX_BYTES = 200 * 1024 * 1024  # 200MB
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty_file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file_too_large")

    cid = ipfs.add_bytes(data, filename=file.filename or "blob")

    # если id_hex задан — проверяем и используем его; иначе считаем sha256(data)
    if id_hex:
        s = id_hex.lower()
        if s.startswith("0x"): s = s[2:]
        if len(s) != 64:
            raise HTTPException(400, "bad_id")
        item_id = bytes.fromhex(s)
    else:
        item_id = hashlib.sha256(data).digest()

    size = len(data)  # ← размер
    checksum32 = Web3.keccak(data)
    mime = file.content_type or ""

    try:
        tx_hash = chain.register_or_update(item_id, cid, checksum32=checksum32, size=size, mime=mime)
    except Exception as e:
        raise HTTPException(502, f"chain_error: {e}")

    return StoreOut(
        id_hex="0x" + item_id.hex(),
        cid=cid,
        tx_hash=tx_hash,
        url=ipfs.url(cid),
    )


class ResolveOut(BaseModel):
    cid: str
    url: str


@router.get("/cid/{id_hex}", response_model=ResolveOut)
def resolve(id_hex: str, chain: Chain = Depends(get_chain), ipfs: IpfsClient = Depends(get_ipfs)):
    if not (isinstance(id_hex, str) and id_hex.startswith("0x") and len(id_hex) == 66):
        raise HTTPException(400, "bad_id")
    cid = chain.cid_of(bytes.fromhex(id_hex[2:]))
    if not cid:
        raise HTTPException(404, "not_found_or_empty_cid")
    return ResolveOut(cid=cid, url=ipfs.url(cid))


class MetaOut(BaseModel):
    owner: str | None = None
    cid: str | None = None
    checksum: str | None = None
    size: int | None = None
    mime: str | None = None
    createdAt: int | None = None


@router.get("/meta/{id_hex}", response_model=MetaOut)
def meta(id_hex: str, chain: Chain = Depends(get_chain)):
    if not (isinstance(id_hex, str) and id_hex.startswith("0x") and len(id_hex) == 66):
        raise HTTPException(400, "bad_id")
    m = chain.meta_of_full(bytes.fromhex(id_hex[2:]))
    # нормализуем
    return MetaOut(
        owner=m.get("owner"),
        cid=m.get("cid"),
        checksum=m.get("checksum") if isinstance(m.get("checksum"), str) else (
            m.get("checksum").hex() if m.get("checksum") else None),
        size=int(m.get("size") or 0),
        mime=m.get("mime"),
        createdAt=int(m.get("createdAt") or 0),
    )


class VersionItem(BaseModel):
    owner: str | None = None
    cid: str | None = None
    checksum: str | None = None  # hex без 0x
    size: int | None = None
    mime: str | None = None
    createdAt: int | None = None


class VersionsOut(BaseModel):
    versions: list[VersionItem]


@router.get("/versions/{id_hex}", response_model=VersionsOut)
def versions(id_hex: str, chain: Chain = Depends(get_chain)):
    if not (isinstance(id_hex, str) and id_hex.startswith("0x") and len(id_hex) == 66):
        raise HTTPException(400, "bad_id")

    raw = chain.versions_of(bytes.fromhex(id_hex[2:]))
    items: list[VersionItem] = []

    for v in raw:
        if not isinstance(v, dict):
            items.append(VersionItem(cid=str(v)))
            continue

        checksum = v.get("checksum")
        if isinstance(checksum, (bytes, bytearray)):
            checksum = checksum.hex()
        elif isinstance(checksum, str) and checksum.startswith("0x"):
            checksum = checksum[2:]
        elif isinstance(checksum, int):
            checksum = f"{checksum:064x}"

        items.append(VersionItem(
            owner=v.get("owner"),
            cid=v.get("cid"),
            checksum=checksum,
            size=int(v.get("size") or 0),
            mime=v.get("mime"),
            createdAt=int(v.get("createdAt") or 0),
        ))

    return VersionsOut(versions=items)


class HistoryItem(BaseModel):
    type: str
    blockNumber: int
    txHash: str
    timestamp: int
    owner: str | None = None
    cid: str | None = None
    checksum: str | None = None  # hex без 0x
    size: int | None = None
    mime: str | None = None


class HistoryOut(BaseModel):
    items: list[HistoryItem]


@router.get("/history/{id_hex}", response_model=HistoryOut)
def history(
        id_hex: str,
        owner: str | None = None,
        type: Literal["FileRegistered", "FileVersioned"] | None = None,
        from_block: int | None = None,
        to_block: int | None = None,
        order: Literal["asc", "desc"] = "asc",
        limit: int = 100,
        chain: Chain = Depends(get_chain),
):
    if not (isinstance(id_hex, str) and id_hex.startswith("0x") and len(id_hex) == 66):
        raise HTTPException(400, "bad_id")

    raw = chain.history(bytes.fromhex(id_hex[2:]), owner=owner)

    if type:
        raw = [e for e in raw if e["type"] == type]
    if from_block is not None:
        raw = [e for e in raw if e["blockNumber"] >= from_block]
    if to_block is not None:
        raw = [e for e in raw if e["blockNumber"] <= to_block]

    raw.sort(key=lambda e: (e["blockNumber"], e["timestamp"]), reverse=(order == "desc"))
    limit = max(1, min(limit, 1000))
    # нормализуем checksum на всякий
    for e in raw:
        cs = e.get("checksum")
        if isinstance(cs, str) and cs.startswith("0x"):
            e["checksum"] = cs[2:]

    return {"items": raw[:limit]}
