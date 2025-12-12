from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

from eth_typing import HexStr
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from web3 import Web3

from app.blockchain.web3_client import Chain
from app.config import settings
from app.deps import get_chain, get_db, rds
from app.models import File, FileVersion, Grant, User
from app.quotas import protect_meta_tx
from app.repos.telegram_repo import get_active_chat_ids_for_addresses
from app.repos.user_repo import get_by_eth_address
from app.schemas.auth import FileCreateIn, TypedDataOut
from app.schemas.common import OkResponse
from app.schemas.grants import DuplicateOut, ShareIn, ShareItemOut, ShareOut
from app.security import get_current_user
from app.services.event_logger import EventLogger
from app.services.event_publisher import EventPublisher
from app.services.notification_publisher import NotificationPublisher
from app.validators import sanitize_filename

router = APIRouter(prefix="/files", tags=["files"])
logger = logging.getLogger(__name__)

AuthorizationHeader = Annotated[str, Header(..., alias="Authorization")]


# ---- auth helper: достаём текущего пользователя из Bearer-токена ----
def require_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user


# ---- NEW: Schema for file list response ----
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
@router.get("", response_model=list[FileListItem])
def list_my_files(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[FileListItem]:
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
        .where(File.owner_id == user.id, File.deleted_at.is_(None))
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
                .where(User.eth_address == user.eth_address.lower(), File.deleted_at.is_(None))
                .order_by(File.created_at.desc())
            )
            fb_files = db.scalars(fallback_q).all()
            if fb_files:
                logger.warning(
                    "list_my_files: fallback by eth_address found %d items for user=%s",
                    len(fb_files),
                    str(user.id),
                )
                files = fb_files
                per_user_count = len(files)
        except Exception as e:
            logger.warning("list_my_files: fallback query failed: %s", e)

    # Log owner_ids of a few recent files for visibility
    try:
        sample = db.execute(
            select(File.owner_id, File.id).where(File.deleted_at.is_(None)).order_by(File.created_at.desc()).limit(5)
        ).all()
        sample_str = ", ".join([f"(owner={row[0]}, id={row[1].hex()})" for row in sample])
    except Exception as e:
        logger.debug("list_my_files: failed to compose sample_str: %s", e, exc_info=True)
        sample_str = "<n/a>"

    try:
        logger.info(
            "list_my_files: dsn=%s user=%s (addr=%s) total_files=%d per_user=%d recent=%s",
            dsn,
            str(user.id),
            user.eth_address,
            per_user_count,
            sample_str,
        )
    except Exception as e:
        logger.debug("list_my_files: failed to emit info log: %s", e, exc_info=True)

    result = []
    for f in files:
        result.append(
            FileListItem(
                id="0x" + f.id.hex(),
                name=f.name or "Unnamed",
                size=f.size,
                mime=f.mime or "application/octet-stream",
                cid=f.cid or "",
                checksum="0x" + f.checksum.hex(),
                created_at=f.created_at.isoformat() if f.created_at else "",
            )
        )

    return result


@router.post("", response_model=TypedDataOut)
def create_file(
    meta: FileCreateIn,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    # Schema validation already enforces fileId/checksum hex32, size<=200MB, mime whitelist, sanitized name
    try:
        fid = Web3.to_bytes(hexstr=cast(HexStr, meta.fileId))
    except Exception as e:
        raise HTTPException(400, "bad_file_id") from e
    try:
        checksum = Web3.to_bytes(hexstr=cast(HexStr, meta.checksum))
    except Exception as e:
        raise HTTPException(400, "bad_checksum") from e

    # Denylist by checksum: Redis set + global DB uniqueness emulation
    try:
        if rds.sismember("denylist:checksum", meta.checksum):
            raise HTTPException(409, "duplicate_checksum")
    except HTTPException:
        raise
    except Exception:
        logger.debug("create_file: denylist check failed for checksum=%s", meta.checksum, exc_info=True)

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
            "to": Web3.to_checksum_address(verifying_contract)
            if verifying_contract != "0x0000000000000000000000000000000000000000"
            else Web3.to_checksum_address("0x0000000000000000000000000000000000000000"),
            "value": 0,
            "gas": 200_000,
            "nonce": nonce_val,
            "data": data_hex32,
        },
    }
    return {"typedData": typed_data}


@router.post("/{id}/share", response_model=ShareOut | DuplicateOut)
def share_file(
    id: str,
    body: ShareIn,
    # dependencies as Annotated to avoid calling Depends() at import time (B008)
    user: Annotated[User, Depends(protect_meta_tx)],
    db: Annotated[Session, Depends(get_db)],
    chain: Annotated[Chain, Depends(get_chain)],
) -> ShareOut | DuplicateOut:
    if not (isinstance(id, str) and id.startswith("0x") and len(id) == 66):
        raise HTTPException(400, "bad_file_id")
    file_id_bytes = Web3.to_bytes(hexstr=cast(HexStr, id))
    file_row: File | None = db.get(File, file_id_bytes)
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
        return DuplicateOut(status="duplicate", capIds=capIds)

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
        raise HTTPException(502, f"chain_unavailable: {e}") from e
    cap_ids_bytes: list[bytes] = []
    cap_ids_hex: list[str] = []
    for idx, (grantee_addr, _) in enumerate(grantees):
        cap_b = chain.predict_cap_id(grantor_addr, grantee_addr, file_id_bytes, nonce=start_nonce, offset=idx)
        cap_ids_bytes.append(cap_b)
        cap_ids_hex.append("0x" + cap_b.hex())
    typed_list: list[dict] = []
    ttl_sec = int(body.ttl_days) * 86400
    to_addr = getattr(ac, "address", grantor_addr)
    for (grantee_addr, _), _cap in zip(grantees, cap_ids_bytes, strict=False):
        call_data = chain.encode_grant_call(file_id_bytes, grantee_addr, ttl_sec, int(body.max_dl))
        td = chain.build_forward_typed_data(from_addr=grantor_addr, to_addr=to_addr, data=call_data, gas=180_000)
        typed_list.append(td)

    # Overwrite idempotency key with final data (no NX to update placeholder)
    try:
        rds.set(
            key,
            _json.dumps({"grantor": grantor_addr, "fileId": id, "capIds": cap_ids_hex}),
            ex=3600,
        )
    except Exception as e:
        logger.debug("share_file: failed to set idempotency key %s: %s", key, e, exc_info=True)

    now = datetime.now(UTC)
    expires_at = now + timedelta(days=int(body.ttl_days))
    for (grantee_addr, grantee_user), cap_b in zip(grantees, cap_ids_bytes, strict=False):
        exists = db.query(Grant).filter(Grant.cap_id == cap_b).one_or_none()
        if exists is not None:
            continue
        enc_b64 = enc_map[grantee_addr.lower()]
        try:
            enc_bytes = base64.b64decode(enc_b64)
        except Exception as e:
            raise HTTPException(400, f"bad_encK_for_{grantee_addr}") from e
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
        for (_grantee_addr, grantee_user), cap_b in zip(grantees, cap_ids_bytes, strict=False):
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

    # Publish notification events for grantor/grantee if chat_id known
    try:
        publisher = NotificationPublisher()
        addr_map = get_active_chat_ids_for_addresses(
            db,
            [user.eth_address] + [ga for ga, _ in grantees],
        )
        for (grantee_addr, _grantee_user), cap_b in zip(grantees, cap_ids_bytes, strict=False):
            cap_hex = "0x" + cap_b.hex()
            grantor_chat = addr_map.get(user.eth_address.lower())
            if grantor_chat:
                publisher.publish(
                    "grant_created",
                    chat_id=grantor_chat,
                    payload={
                        "capId": cap_hex,
                        "fileId": id,
                        "grantor": user.eth_address,
                        "grantee": grantee_addr,
                        "ttlDays": int(body.ttl_days),
                        "maxDownloads": int(body.max_dl),
                        "expiresAt": expires_at.isoformat(),
                    },
                    event_id=f"grant_created:{cap_hex}:{grantor_chat}",
                )
            grantee_chat = addr_map.get(grantee_addr.lower())
            if grantee_chat:
                publisher.publish(
                    "grant_received",
                    chat_id=grantee_chat,
                    payload={
                        "capId": cap_hex,
                        "fileId": id,
                        "grantor": user.eth_address,
                        "grantee": grantee_addr,
                        "ttlDays": int(body.ttl_days),
                        "maxDownloads": int(body.max_dl),
                        "expiresAt": expires_at.isoformat(),
                    },
                    event_id=f"grant_received:{cap_hex}:{grantee_chat}",
                )
                # Сразу отправляем download_allowed для генерации одноразовой ссылки
                try:
                    file_obj = db.get(File, file_id_bytes)
                    file_name = file_obj.name if file_obj else None
                    publisher.publish(
                        "download_allowed",
                        chat_id=grantee_chat,
                        payload={
                            "capId": cap_hex,
                            "fileId": id,
                            "fileName": file_name,
                        },
                        event_id=f"download_allowed:{cap_hex}:{grantee_chat}",
                    )
                except Exception as e:
                    logger.debug("Failed to publish download_allowed for %s: %s", cap_hex, e)
    except Exception as e:
        logger.warning("Failed to publish notification events for grants: %s", e, exc_info=True)

    items = [
        ShareItemOut(grantee=addr_lower_to_input[ga.lower()], capId=ch, status="queued")
        for (ga, _), ch in zip(grantees, cap_ids_hex, strict=False)
    ]
    return ShareOut(items=items, typedDataList=typed_list)


@router.delete("/{id}", response_model=OkResponse)
def delete_file(
    id: str,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    chain: Annotated[Chain, Depends(get_chain)],
) -> OkResponse:
    """
    Soft-delete file: mark deleted_at, revoke active grants, publish event.
    """
    if not (isinstance(id, str) and id.startswith("0x") and len(id) == 66):
        raise HTTPException(400, "bad_file_id")
    try:
        file_id_bytes = Web3.to_bytes(hexstr=cast(HexStr, id))
    except Exception as e:
        raise HTTPException(400, "bad_file_id") from e

    file_obj: File | None = db.get(File, file_id_bytes)
    if file_obj is None or file_obj.deleted_at is not None:
        raise HTTPException(404, "file_not_found")
    if file_obj.owner_id != user.id:
        raise HTTPException(403, "not_owner")

    now = datetime.now(UTC)
    file_obj.deleted_at = now

    # Revoke active grants
    active_grants = db.query(Grant).filter(Grant.file_id == file_id_bytes, Grant.revoked_at.is_(None)).all()
    for g in active_grants:
        g.revoked_at = now
        g.status = "revoked"
        db.add(g)

    db.add(file_obj)
    db.commit()

    # Publish notification to owner chat if available
    try:
        publisher = NotificationPublisher()
        chat_map = get_active_chat_ids_for_addresses(db, [user.eth_address])
        chat_id = chat_map.get(user.eth_address.lower())
        if chat_id:
            publisher.publish(
                "file_deleted",
                chat_id=chat_id,
                payload={"fileId": id},
                event_id=f"file_deleted:{id}:{chat_id}",
            )
    except Exception as e:
        logger.warning("Failed to publish file_deleted notification: %s", e, exc_info=True)

    try:
        EventPublisher().publish(
            "file_deleted",
            subject={"fileId": id, "owner": user.eth_address},
            payload={"ts": now.isoformat()},
            event_id=f"file_deleted:{id}",
        )
    except Exception as e:
        logger.debug("Failed to log file_deleted event: %s", e, exc_info=True)

    return OkResponse()


@router.get("/{id}/grants")
def list_file_grants(
    id: str,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
    chain: Annotated[Chain, Depends(get_chain)],
) -> dict[str, Any]:
    # Validate file id (0x + 64)
    if not (isinstance(id, str) and id.startswith("0x") and len(id) == 66):
        raise HTTPException(400, "bad_file_id")
    try:
        file_id_bytes = Web3.to_bytes(hexstr=cast(HexStr, id))
    except Exception as e:
        raise HTTPException(400, "bad_file_id") from e

    # Ensure file exists and belongs to current user
    file_row: File | None = db.get(File, file_id_bytes)
    if file_row is None:
        raise HTTPException(404, "file_not_found")
    if file_row.deleted_at is not None:
        raise HTTPException(404, "file_not_found")
    if file_row.owner_id != user.id:
        raise HTTPException(403, "not_owner")

    # Collect grants joined with grantee address
    rows = db.execute(
        select(Grant, User.eth_address)
        .join(User, Grant.grantee_id == User.id)
        .where(Grant.file_id == file_id_bytes, Grant.revoked_at.is_(None))
        .order_by(Grant.created_at.desc())
    ).all()

    from datetime import datetime

    now = datetime.now(UTC)

    # Try to use on-chain info when possible
    items = []
    ac = None
    try:
        ac = chain.get_access_control()
    except Exception as e:
        logger.debug("list_file_grants: failed to get access control: %s", e, exc_info=True)
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
                    expires_at_iso = (
                        datetime.fromtimestamp(on_expires_at, tz=UTC).isoformat() if on_expires_at else expires_at_iso
                    )
                    if on_revoked:
                        status = "revoked"
                    elif now.timestamp() > on_expires_at and on_expires_at:
                        status = "expired"
                    elif on_used >= on_max and on_max:
                        status = "exhausted"
                    else:
                        status = "confirmed"
            except Exception as e:
                # fallback below; log for diagnostics
                logger.debug("list_file_grants: on-chain grants read failed for cap %s: %s", cap_hex, e, exc_info=True)
        if ac is None:
            if g.revoked_at is not None:
                status = "revoked"
            elif now > g.expires_at:
                status = "expired"
            elif int(g.used or 0) >= int(g.max_dl or 0):
                status = "exhausted"

        items.append(
            {
                "grantee": grantee_addr,
                "capId": cap_hex,
                "maxDownloads": max_dl,
                "usedDownloads": used,
                "expiresAt": expires_at_iso,
                "status": status,
            }
        )

    return {"items": items}


class FileRenameIn(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("bad_name")
        return sanitize_filename(v)


@router.patch("/{id}")
def rename_file(
    id: str,
    body: FileRenameIn,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    """Allow file owner to rename a file's display name.

    Does not modify history/versions or public link snapshots.
    """
    if not (isinstance(id, str) and id.startswith("0x") and len(id) == 66):
        raise HTTPException(400, "bad_file_id")
    try:
        file_id = Web3.to_bytes(hexstr=cast(HexStr, id))
    except Exception as e:
        raise HTTPException(400, "bad_file_id") from e

    file_row: File | None = db.get(File, file_id)
    if file_row is None:
        raise HTTPException(404, "file_not_found")
    if file_row.owner_id != user.id:
        raise HTTPException(403, "forbidden")

    old_name = file_row.name
    new_name = body.name
    # Update only display name
    file_row.name = new_name
    db.add(file_row)
    db.commit()

    # Audit log
    try:
        ev = EventLogger(db)
        ev.log_event(
            event_type="file_renamed",
            payload={
                "file_id": file_row.id.hex(),
                "old_name": str(old_name),
                "new_name": str(new_name),
                "user_id": str(user.id),
            },
            user_id=user.id,
        )
    except Exception:
        logger.debug("rename_file: failed to log event", exc_info=True)

    return {
        "idHex": "0x" + file_row.id.hex(),
        "name": file_row.name,
        "size": file_row.size,
        "mime": file_row.mime,
        "cid": file_row.cid,
        "checksum": "0x" + (file_row.checksum.hex() if file_row.checksum else ""),
        "createdAt": int(file_row.created_at.timestamp()) if file_row.created_at else 0,
    }
