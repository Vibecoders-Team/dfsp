from __future__ import annotations

import uuid
from typing import Any, Optional, cast, Union, List
from typing_extensions import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from web3 import Web3
from eth_typing import HexStr

from app.deps import get_db, get_chain, rds
from app.models import File, FileVersion, User, Grant
from app.schemas.auth import FileCreateIn, TypedDataOut
from app.schemas.grants import ShareIn, ShareOut, ShareItemOut, DuplicateOut
from app.security import parse_token
from app.quotas import protect_meta_tx

import base64
from datetime import datetime, timedelta, timezone
from app.repos.user_repo import get_by_eth_address
from sqlalchemy.exc import IntegrityError
import logging
from app.config import settings
from app.services.event_logger import EventLogger

router = APIRouter(prefix="/files", tags=["files"])
logger = logging.getLogger(__name__)

AuthorizationHeader = Annotated[str, Header(..., alias="Authorization")]


# ---- auth helper: достаём текущего пользователя из Bearer-токена ----
def require_user(authorization: AuthorizationHeader, db: Session = Depends(get_db)) -> User:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "auth_required")
    try:
        payload = parse_token(token)
        sub = getattr(payload, "sub", None) or payload.get("sub")
        user_id = uuid.UUID(str(sub))
    except Exception:
        raise HTTPException(401, "bad_token")
    user_obj: Optional[User] = db.get(User, user_id)
    if user_obj is None:
        raise HTTPException(401, "user_not_found")
    return user_obj


# ---- NEW: Schema for file list response ----
from pydantic import BaseModel

class FileListItem(BaseModel):
    id: str  # hex string
    name: str
    size: int
    mime: str
    cid: str
    checksum: str  # hex string
    created_at: str  # ISO timestamp

    class Config:
        from_attributes = True


# ---- GET /files - List all files for current user ----
@router.get("", response_model=List[FileListItem])
def list_my_files(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Возвращает список всех файлов текущего пользователя
    """
    # Extra diagnostics
    try:
        dsn = settings.postgres_dsn
    except Exception:
        dsn = "<unknown>"

    # Count total files and per-user count for diagnostics
    total_files = db.query(File).count()
    user_files_q = (
        select(File)
        .where(File.owner_id == user.id)
        .order_by(File.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    files = db.scalars(user_files_q).all()
    per_user_count = len(files)

    # Fallback: join on users.eth_address if nothing found (diagnostic/workaround)
    if per_user_count == 0:
        try:
            fallback_q = (
                select(File)
                .join(User, File.owner_id == User.id)
                .where(User.eth_address == user.eth_address.lower())
                .order_by(File.created_at.desc())
            )
            fb_files = db.scalars(fallback_q).all()
            if fb_files:
                logger.warning(
                    "list_my_files: fallback by eth_address found %d items for user=%s",
                    len(fb_files), str(user.id)
                )
                files = fb_files
                per_user_count = len(files)
        except Exception as e:
            logger.warning("list_my_files: fallback query failed: %s", e)

    # Log owner_ids of a few recent files for visibility
    try:
        sample = db.execute(select(File.owner_id, File.id).order_by(File.created_at.desc()).limit(5)).all()
        sample_str = ", ".join([f"(owner={row[0]}, id={row[1].hex()})" for row in sample])
    except Exception:
        sample_str = "<n/a>"

    try:
        logger.info(
            "list_my_files: dsn=%s user=%s total_files=%d per_user=%d recent=%s",
            dsn, str(user.id), total_files, per_user_count, sample_str
        )
    except Exception:
        pass

    result = []
    for f in files:
        result.append(FileListItem(
            id="0x" + f.id.hex(),
            name=f.name or "Unnamed",
            size=f.size,
            mime=f.mime or "application/octet-stream",
            cid=f.cid or "",
            checksum="0x" + f.checksum.hex(),
            created_at=f.created_at.isoformat() if f.created_at else "",
        ))

    return result


@router.post("", response_model=TypedDataOut)
def create_file(
        meta: FileCreateIn,
        user: User = Depends(require_user),
        db: Session = Depends(get_db),
):
    # Schema validation already enforces fileId/checksum hex32, size<=200MB, mime whitelist, sanitized name
    try:
        fid = Web3.to_bytes(hexstr=cast(HexStr, meta.fileId))
    except Exception:
        raise HTTPException(400, "bad_file_id")
    try:
        checksum = Web3.to_bytes(hexstr=cast(HexStr, meta.checksum))
    except Exception:
        raise HTTPException(400, "bad_checksum")

    # Denylist by checksum: Redis set + global DB uniqueness emulation
    try:
        if rds.sismember("denylist:checksum", meta.checksum):
            raise HTTPException(409, "duplicate_checksum")
    except HTTPException:
        raise
    except Exception:
        pass

    exists = db.scalar(select(File.id).where(File.id == fid))
    if exists:
        raise HTTPException(409, "already_registered")

    # Global duplicate by checksum across all users
    dup_global = db.scalar(select(File.id).where(File.checksum == checksum))
    if dup_global:
        raise HTTPException(409, "duplicate_checksum")

    file = File(
        id=fid,
        owner_id=user.id,
        name=meta.name,
        size=int(meta.size),
        mime=meta.mime,
        cid=meta.cid,
        checksum=checksum,
    )
    db.add(file)
    db.flush()
    ver = FileVersion(
        file_id=file.id,
        version=1,
        cid=file.cid,
        checksum=file.checksum,
        size=file.size,
        mime=file.mime,
    )
    db.add(ver)

    # Log event for anchoring
    try:
        event_logger = EventLogger(db)
        event_logger.log_file_registered(
            file_id=file.id,
            owner_id=user.id,
            cid=file.cid,
            checksum=file.checksum,
            size=file.size,
        )
    except Exception as e:
        logger.warning(f"Failed to log file_registered event: {e}")

    db.commit()

    # Try to build typed data via chain, fallback to placeholders if chain is unavailable
    fwd = None
    fwd_addr: Optional[str] = None
    chain_id_val: int = 31337
    verifying_contract = "0x0000000000000000000000000000000000000000"
    nonce_val: int = 0
    try:
        chain = get_chain()
        chain_id_val = int(getattr(chain, "chain_id", 31337))
        fwd = chain.contracts.get("MinimalForwarder")
        addr = getattr(fwd, "address", None) if fwd is not None else None
        if isinstance(addr, str):
            verifying_contract = Web3.to_checksum_address(addr)
        else:
            # try eip712Domain on forwarder
            try:
                verifying_contract = Web3.to_checksum_address(chain.get_forwarder().address)
            except Exception:
                verifying_contract = verifying_contract
        if fwd is not None:
            signer = Web3.to_checksum_address(user.eth_address)
            try:
                nonce_raw = cast(Any, fwd).functions.getNonce(signer).call()
                nonce_val = int(nonce_raw)
            except Exception:
                nonce_val = 0
    except Exception as e:
        logger.warning("create_file: chain unavailable, using placeholders: %s", e)

    data_hex32 = meta.checksum
    typed_data = {
        "domain": {
            "name": "MinimalForwarder",
            "version": "0.0.1",
            "chainId": chain_id_val,
            "verifyingContract": verifying_contract,
        },
        "types": {
            "ForwardRequest": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "gas", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "data", "type": "bytes"},
            ]
        },
        "primaryType": "ForwardRequest",
        "message": {
            "from": Web3.to_checksum_address(user.eth_address),
            "to": Web3.to_checksum_address(verifying_contract) if verifying_contract != "0x0000000000000000000000000000000000000000" else Web3.to_checksum_address("0x0000000000000000000000000000000000000000"),
            "value": 0,
            "gas": 200_000,
            "nonce": nonce_val,
            "data": data_hex32,
        },
    }
    return {"typedData": typed_data}


@router.post("/{id}/share", response_model=Union[ShareOut, DuplicateOut])
def share_file(
    id: str,
    body: ShareIn,
    # Заменяем `Depends(require_user)` на нашу новую зависимость-защитник
    user: User = Depends(protect_meta_tx),
    db: Session = Depends(get_db),
    chain=Depends(get_chain),
):
    if not (isinstance(id, str) and id.startswith("0x") and len(id) == 66):
        raise HTTPException(400, "bad_file_id")
    file_id_bytes = Web3.to_bytes(hexstr=cast(HexStr, id))
    file_row: Optional[File] = db.get(File, file_id_bytes)
    if file_row is None:
        raise HTTPException(404, "file_not_found")
    if file_row.owner_id != user.id:
        raise HTTPException(403, "not_owner")
    import json as _json
    key = f"share:req:{body.request_id}"

    # Reserve idempotency key early to avoid races. If present, return duplicate.
    try:
        reserved = rds.set(key, "{}", ex=3600, nx=True)
    except Exception:
        reserved = True  # fail-open: proceed normally
    if not reserved:
        try:
            existing = rds.get(key)
        except Exception:
            existing = None
        if existing:
            try:
                if isinstance(existing, bytes):
                    existing_str = existing.decode("utf-8", errors="ignore")
                else:
                    existing_str = str(existing)
                data = _json.loads(existing_str)
                capIds = data.get("capIds") or []
            except Exception:
                capIds = []
        else:
            capIds = []
        return {"status": "duplicate", "capIds": capIds}

    addr_lower_to_input = {a.lower(): a for a in body.users}
    enc_map = {k.lower(): v for k, v in (body.encK_map or {}).items()}
    grantees: list[tuple[str, User]] = []
    for addr_in in body.users:
        if addr_in.lower() not in enc_map:
            raise HTTPException(400, f"encK_missing_for_{addr_in}")
        u = get_by_eth_address(db, addr_in)
        if u is None:
            raise HTTPException(400, f"unknown_grantee_{addr_in}")
        grantees.append((Web3.to_checksum_address(addr_in), u))
    ac = chain.get_access_control()
    grantor_addr = Web3.to_checksum_address(user.eth_address)
    try:
        start_nonce = int(chain.read_grant_nonce_cached(grantor_addr))
    except Exception as e:
        raise HTTPException(502, f"chain_unavailable: {e}")
    cap_ids_bytes: list[bytes] = []
    cap_ids_hex: list[str] = []
    for idx, (grantee_addr, _) in enumerate(grantees):
        cap_b = chain.predict_cap_id(grantor_addr, grantee_addr, file_id_bytes, nonce=start_nonce, offset=idx)
        cap_ids_bytes.append(cap_b)
        cap_ids_hex.append("0x" + cap_b.hex())
    typed_list: list[dict] = []
    ttl_sec = int(body.ttl_days) * 86400
    to_addr = getattr(ac, "address", grantor_addr)
    for (grantee_addr, _), _cap in zip(grantees, cap_ids_bytes):
        call_data = chain.encode_grant_call(file_id_bytes, grantee_addr, ttl_sec, int(body.max_dl))
        td = chain.build_forward_typed_data(from_addr=grantor_addr, to_addr=to_addr, data=call_data, gas=180_000)
        typed_list.append(td)

    # Overwrite idempotency key with final data (no NX to update placeholder)
    try:
        rds.set(key, _json.dumps({"grantor": grantor_addr, "fileId": id, "capIds": cap_ids_hex}), ex=3600)
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=int(body.ttl_days))
    for (grantee_addr, grantee_user), cap_b in zip(grantees, cap_ids_bytes):
        exists = db.query(Grant).filter(Grant.cap_id == cap_b).one_or_none()
        if exists is not None:
            continue
        enc_b64 = enc_map[grantee_addr.lower()]
        try:
            enc_bytes = base64.b64decode(enc_b64)
        except Exception:
            raise HTTPException(400, f"bad_encK_for_{grantee_addr}")
        grant = Grant(
            cap_id=cap_b,
            file_id=file_id_bytes,
            grantor_id=user.id,
            grantee_id=grantee_user.id,
            expires_at=expires_at,
            max_dl=int(body.max_dl),
            used=0,
            revoked_at=None,
            status="pending",
            tx_hash=None,
            confirmed_at=None,
            enc_key=enc_bytes,
        )
        db.add(grant)
    try:
        db.commit()
    except IntegrityError as ie:
        db.rollback()
        if "uq_grants_cap_id" not in str(ie.orig) if hasattr(ie, "orig") else str(ie):
            raise

    # Log grant_created events for all new grants
    try:
        event_logger = EventLogger(db)
        for (grantee_addr, grantee_user), cap_b in zip(grantees, cap_ids_bytes):
            event_logger.log_grant_created(
                cap_id=cap_b,
                file_id=file_id_bytes,
                grantor_id=user.id,
                grantee_id=grantee_user.id,
                ttl_seconds=ttl_sec,
                max_downloads=int(body.max_dl),
            )
    except Exception as e:
        logger.warning(f"Failed to log grant_created events: {e}")

    items = [ShareItemOut(grantee=addr_lower_to_input[ga.lower()], capId=ch, status="queued") for (ga, _), ch in zip(grantees, cap_ids_hex)]
    return ShareOut(items=items, typedDataList=typed_list)


@router.get("/{id}/grants")
def list_file_grants(
    id: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    chain=Depends(get_chain),
):
    # Validate file id (0x + 64)
    if not (isinstance(id, str) and id.startswith("0x") and len(id) == 66):
        raise HTTPException(400, "bad_file_id")
    try:
        file_id_bytes = Web3.to_bytes(hexstr=cast(HexStr, id))
    except Exception:
        raise HTTPException(400, "bad_file_id")

    # Ensure file exists and belongs to current user
    file_row: Optional[File] = db.get(File, file_id_bytes)
    if file_row is None:
        raise HTTPException(404, "file_not_found")
    if file_row.owner_id != user.id:
        raise HTTPException(403, "not_owner")

    # Collect grants joined with grantee address
    rows = db.execute(
        select(Grant, User.eth_address)
        .join(User, Grant.grantee_id == User.id)
        .where(Grant.file_id == file_id_bytes)
        .order_by(Grant.created_at.desc())
    ).all()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    # Try to use on-chain info when possible
    items = []
    ac = None
    try:
        ac = chain.get_access_control()
    except Exception:
        ac = None

    for g, grantee_addr in rows:
        cap_hex = "0x" + bytes(g.cap_id).hex()
        status = (g.status or "pending").lower()
        used = int(g.used or 0)
        max_dl = int(g.max_dl or 0)
        expires_at_iso = g.expires_at.isoformat()

        if ac is not None:
            try:
                gg = ac.functions.grants(bytes(g.cap_id)).call()
                on_expires_at = int(gg[3]) if gg and len(gg) >= 4 else 0
                on_max = int(gg[4]) if gg and len(gg) >= 5 else 0
                on_used = int(gg[5]) if gg and len(gg) >= 6 else 0
                on_revoked = bool(gg[7]) if gg and len(gg) >= 8 else False
                if gg and len(gg) >= 7 and int(gg[6]) == 0:
                    status = "pending"
                else:
                    used = on_used
                    max_dl = on_max
                    expires_at_iso = datetime.fromtimestamp(on_expires_at, tz=timezone.utc).isoformat() if on_expires_at else expires_at_iso
                    if on_revoked:
                        status = "revoked"
                    elif now.timestamp() > on_expires_at and on_expires_at:
                        status = "expired"
                    elif on_used >= on_max and on_max:
                        status = "exhausted"
                    else:
                        status = "confirmed"
            except Exception:
                # fallback below
                pass
        if ac is None:
            if g.revoked_at is not None:
                status = "revoked"
            elif now > g.expires_at:
                status = "expired"
            elif int(g.used or 0) >= int(g.max_dl or 0):
                status = "exhausted"

        items.append({
            "grantee": grantee_addr,
            "capId": cap_hex,
            "maxDownloads": max_dl,
            "usedDownloads": used,
            "expiresAt": expires_at_iso,
            "status": status,
        })

    return {"items": items}
