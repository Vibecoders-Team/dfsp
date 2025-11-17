from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from web3 import Web3

from app.blockchain.web3_client import Chain
from app.config import settings

# --- ИЗМЕНЕНИЯ ЗДЕСЬ (Импорты) ---
from app.deps import get_chain, get_db, get_ipfs
from app.ipfs.client import IpfsClient
from app.models import File as FileModel

# --- ИЗМЕНЕНИЯ ЗДЕСЬ (Импорты) ---
from app.models import FileVersion, User
from app.security import get_current_user  # guard

router = APIRouter(prefix="/storage", tags=["storage"])
log = logging.getLogger(__name__)


class StoreOut(BaseModel):
    id_hex: str
    cid: str
    tx_hash: str
    url: str


@router.post("/store", response_model=StoreOut)
async def store_file(
    file: UploadFile = File(...),
    id_hex: str | None = Form(None),
    checksum: str | None = Form(None),
    plain_size: int | None = Form(None),
    orig_name: str | None = Form(None),
    orig_mime: str | None = Form(None),
    chain: Chain = Depends(get_chain),
    ipfs: IpfsClient = Depends(get_ipfs),
    # --- ИЗМЕНЕНИЯ ЗДЕСЬ (Зависимость) ---
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StoreOut:
    MAX_BYTES = 200 * 1024 * 1024  # 200MB
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty_file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file_too_large")

    cid = ipfs.add_bytes(data, filename=file.filename or "blob")

    # Compute initial item_id
    if id_hex:
        s = id_hex.lower()
        if s.startswith("0x"):
            s = s[2:]
        if len(s) != 64:
            raise HTTPException(400, "bad_id")
        item_id = bytes.fromhex(s)
    else:
        # fallback: derive from uploaded bytes (encrypted/plain depending on caller)
        import hashlib as _hashlib

        item_id = _hashlib.sha256(data).digest()

    # Prefer provided checksum (hex) and plain_size
    checksum32 = None
    if isinstance(checksum, str) and checksum:
        ss = checksum.strip().lower()
        if ss.startswith("0x"):
            ss = ss[2:]
        try:
            raw = bytes.fromhex(ss)
            if len(raw) != 32:
                raise ValueError("bad_len")
            checksum32 = raw
        except Exception:
            raise HTTPException(400, "bad_checksum")
    if checksum32 is None:
        checksum32 = Web3.keccak(data)

    size = int(plain_size) if isinstance(plain_size, int) and plain_size is not None else len(data)
    # MIME: предпочитаем оригинальный (plaintext), а не тип зашифрованного blob'а
    mime = (orig_mime or "").strip() or ""

    # Определяем исходное имя файла (без .enc)
    the_name = (orig_name or "").strip() or (file.filename or "untitled")
    if the_name.lower().endswith(".enc"):
        the_name = the_name[:-4]

    # Log DSN for diagnosing cross-DB issues
    try:
        log.info("store_file: dsn=%s", settings.postgres_dsn)
    except Exception:
        log.debug("store_file: failed to read settings.postgres_dsn", exc_info=True)

    # If another owner already has this item_id, switch to a per-user id to avoid cross-user collision
    try:
        existing = db.get(FileModel, item_id)
    except Exception:
        existing = None
    if existing is not None and existing.owner_id != user.id:
        # Даже если id_hex был явно предоставлен клиентом — не даём перезаписать чужой файл.
        base_seed = user.id.bytes + bytes(checksum32)
        attempt = 0
        while True:
            candidate = (
                Web3.keccak(base_seed + attempt.to_bytes(4, "big"))
                if attempt
                else Web3.keccak(base_seed)
            )
            other = db.get(FileModel, candidate)
            if other is None or other.owner_id == user.id:
                log.info(
                    "store_file: collision for id=%s (owned by %s) -> reassigned to %s (attempt=%d)",
                    item_id.hex(),
                    existing.owner_id,
                    candidate.hex(),
                    attempt,
                )
                item_id = candidate
                break
            attempt += 1
            if attempt > 25:
                raise HTTPException(500, "collision_resolution_failed")

    # Debug: log user and file identifiers before chain/db ops
    try:
        log.info(
            "store_file: user_id=%s eth=%s filename=%s item_id=%s size=%d mime=%s",
            str(user.id),
            user.eth_address,
            (file.filename or ""),
            item_id.hex(),
            size,
            mime,
        )
    except Exception:
        log.debug("store_file: failed to emit debug info log", exc_info=True)

    try:
        tx_hash = chain.register_or_update(
            item_id, cid, checksum32=checksum32, size=size, mime=mime
        )
    except Exception as e:
        log.error(f"Chain transaction failed: {e}", exc_info=True)
        raise HTTPException(502, f"chain_error: {e}")

    try:
        # Проверяем, существует ли уже запись, чтобы обновить ее (логика update)
        db_file = db.get(FileModel, item_id)
        if db_file:
            db_file.cid = cid
            db_file.checksum = checksum32
            db_file.size = size
            db_file.mime = mime or db_file.mime
            db_file.name = the_name or db_file.name

            # Создаем новую версию
            from sqlalchemy import func, select

            latest_version = (
                db.scalar(
                    select(func.max(FileVersion.version)).where(FileVersion.file_id == item_id)
                )
                or 0
            )

            new_version = FileVersion(
                file_id=item_id,
                version=latest_version + 1,
                cid=cid,
                checksum=checksum32,
                size=size,
                mime=mime or db_file.mime,
            )
            db.add(new_version)
        else:
            # Если файла нет, создаем новую запись (логика register)
            db_file = FileModel(
                id=item_id,
                owner_id=user.id,
                name=the_name,
                size=size,
                mime=mime,
                cid=cid,
                checksum=checksum32,
            )
            db.add(db_file)
            db.flush()  # Чтобы получить ID перед созданием версии

            # Создаем первую версию
            first_version = FileVersion(
                file_id=item_id,
                version=1,
                cid=cid,
                checksum=checksum32,
                size=size,
                mime=mime,
            )
            db.add(first_version)

        db.commit()
        log.info(
            "File %s saved to database successfully (owner_id=%s)", item_id.hex(), str(user.id)
        )

    except Exception as e:
        db.rollback()
        log.error(
            f"DATABASE FAILED after successful chain transaction {tx_hash}: {e}", exc_info=True
        )
        # Сообщаем об ошибке, чтобы фронт не считал загрузку успешной
        raise HTTPException(500, "db_error")

    return StoreOut(
        id_hex="0x" + item_id.hex(),
        cid=cid,
        tx_hash=tx_hash,
        url=ipfs.url(cid),
    )


# ... (остальная часть файла остается без изменений)
class ResolveOut(BaseModel):
    cid: str
    url: str


@router.get("/cid/{id_hex}", response_model=ResolveOut)
def resolve(id_hex: str, chain: Chain = Depends(get_chain), ipfs: IpfsClient = Depends(get_ipfs)) -> ResolveOut:
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
    name: str | None = None


@router.get("/meta/{id_hex}", response_model=MetaOut)
def meta(id_hex: str, chain: Chain = Depends(get_chain), db: Session = Depends(get_db)) -> MetaOut:
    if not (isinstance(id_hex, str) and id_hex.startswith("0x") and len(id_hex) == 66):
        raise HTTPException(400, "bad_id")
    # Get on-chain meta
    m: dict[str, Any] = chain.meta_of_full(bytes.fromhex(id_hex[2:]))
    # Try to fetch off-chain DB record for optional fields like `name`
    file_name: str | None = None
    try:
        file_id_bytes = bytes.fromhex(id_hex[2:])
        db_file = db.get(FileModel, file_id_bytes)
        if db_file and getattr(db_file, "name", None):
            file_name = db_file.name
    except Exception:
        file_name = None

    cs = m.get("checksum")
    if isinstance(cs, (bytes, bytearray)):
        checksum = cs.hex()
    elif isinstance(cs, str):
        checksum = cs
    else:
        checksum = None

    return MetaOut(
        owner=m.get("owner"),
        cid=m.get("cid"),
        checksum=checksum,
        size=int(m.get("size") or 0),
        mime=m.get("mime"),
        createdAt=int(m.get("createdAt") or 0),
        name=file_name,
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
def versions(id_hex: str, chain: Chain = Depends(get_chain)) -> VersionsOut:
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

        items.append(
            VersionItem(
                owner=v.get("owner"),
                cid=v.get("cid"),
                checksum=checksum,
                size=int(v.get("size") or 0),
                mime=v.get("mime"),
                createdAt=int(v.get("createdAt") or 0),
            )
        )

    return VersionsOut(versions=items)


class HistoryItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)  # можно и без этого, но полезно
    event_type: str = Field(alias="type")
    blockNumber: int
    txHash: str
    timestamp: int
    owner: str | None = None
    cid: str | None = None
    checksum: str | None = None
    size: int | None = None
    mime: str | None = None


class HistoryOut(BaseModel):
    items: list[HistoryItem]


@router.get("/history/{id_hex}", response_model=HistoryOut)
def history(
    id_hex: str,
    owner: str | None = None,
    event_type: Literal["FileRegistered", "FileVersioned"] | None = None,
    from_block: int | None = None,
    to_block: int | None = None,
    order: Literal["asc", "desc"] = "asc",
    limit: int = 100,
    chain: Chain = Depends(get_chain),
) -> HistoryOut:
    if not (isinstance(id_hex, str) and id_hex.startswith("0x") and len(id_hex) == 66):
        raise HTTPException(400, "bad_id")

    raw = chain.history(bytes.fromhex(id_hex[2:]), owner=owner)

    if event_type:
        raw = [e for e in raw if (e.get("type") or e.get("event_type")) == event_type]
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
