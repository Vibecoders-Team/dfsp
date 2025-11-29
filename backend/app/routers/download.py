from __future__ import annotations

import base64
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from eth_typing import HexStr
from fastapi import APIRouter, Depends, Header, HTTPException
from redis.exceptions import ResponseError
from sqlalchemy import select
from sqlalchemy.orm import Session
from web3 import Web3

from app.blockchain.web3_client import Chain
from app.cache import Cache
from app.deps import get_chain, get_db, rds
from app.models import File, Grant, User
from app.quotas import QuotaManager, protect_download
from app.repos.telegram_repo import get_active_chat_id_for_user
from app.security import parse_token
from app.services.event_logger import EventLogger
from app.services.notification_publisher import NotificationPublisher

router = APIRouter(prefix="/download", tags=["download"])
logger = logging.getLogger(__name__)

# ... (функция require_user остается без изменений)
AuthorizationHeader = Annotated[str, Header(..., alias="Authorization")]

ZERO_ADDR = "0x0000000000000000000000000000000000000000"
DL_ONCE_TTL = 300
PUBLIC_WEB_ORIGIN = os.getenv("PUBLIC_WEB_ORIGIN", "http://localhost:3000").rstrip("/")


def require_user(authorization: AuthorizationHeader, db: Annotated[Session, Depends(get_db)]) -> User:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "auth_required")
    try:
        payload = parse_token(token)
        sub = getattr(payload, "sub", None) or payload.get("sub")
        user_id = cast("uuid.UUID", uuid.UUID(str(sub)))
    except Exception as e:
        raise HTTPException(401, "bad_token") from e
    user_obj: User | None = db.get(User, user_id)
    if user_obj is None:
        raise HTTPException(401, "user_not_found")
    return user_obj


def _publish_download_event(
    db: Session,
    user: User,
    cap_id: str,
    event_type: str,
    *,
    reason: str | None = None,
) -> None:
    """Публикует download_allowed/denied если есть chat_id."""
    try:
        chat_id = get_active_chat_id_for_user(db, user)
        if not chat_id:
            return
        payload: dict[str, Any] = {"capId": cap_id}
        if reason:
            payload["reason"] = reason
        NotificationPublisher().publish(
            event_type,
            chat_id=chat_id,
            payload=payload,
            event_id=f"{event_type}:{cap_id}:{chat_id}",
        )
    except Exception as e:
        logger.debug("Failed to publish %s event for %s: %s", event_type, cap_id, e, exc_info=True)


def _build_download_payload(
    db: Session,
    chain: Chain,
    user: User,
    grant: Grant,
    cap_id: str,
) -> dict[str, Any]:
    cap_b = grant.cap_id
    file_id_bytes = grant.file_id
    now = datetime.now(UTC)
    revoked = False
    expired = False
    exhausted = False
    try:
        ac = chain.get_access_control()
        g = ac.functions.grants(cap_b).call()
        on_grantee = Web3.to_checksum_address(g[1]) if g and len(g) >= 2 else None
        on_file_id = g[2] if g and len(g) >= 3 else None
        on_expires_at = int(g[3]) if g and len(g) >= 4 else 0
        on_max = int(g[4]) if g and len(g) >= 5 else 0
        on_used = int(g[5]) if g and len(g) >= 6 else 0
        on_revoked = bool(g[7]) if g and len(g) >= 8 else False
        if g and len(g) >= 7 and int(g[6]) == 0:
            raise RuntimeError("not_mined_yet")
        if on_grantee and on_grantee.lower() != user.eth_address.lower():
            raise HTTPException(403, "not_grantee")
        revoked = on_revoked
        expired = now.timestamp() > on_expires_at if on_expires_at else False
        exhausted = on_used >= on_max if on_max else True
        file_id_bytes = bytes(on_file_id) if isinstance(on_file_id, (bytes, bytearray)) else grant.file_id
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("prepare_download: on-chain grants lookup failed for %s: %s", cap_id, e, exc_info=True)
        revoked = grant.revoked_at is not None or (grant.status == "revoked")
        expired = now > grant.expires_at
        exhausted = int(grant.used or 0) >= int(grant.max_dl or 0)
        file_id_bytes = grant.file_id

    if revoked:
        raise HTTPException(403, "revoked")
    if expired:
        raise HTTPException(403, "expired")
    if exhausted:
        raise HTTPException(403, "exhausted")

    cid = ""
    try:
        cid = chain.cid_of(file_id_bytes) or ""
    except Exception as e:
        logger.debug("prepare_download: chain.cid_of failed for %s: %s", file_id_bytes, e, exc_info=True)
    if not cid:
        f: File | None = db.get(File, file_id_bytes)
        if f and f.cid:
            cid = f.cid
    if not cid:
        raise HTTPException(502, "registry_unavailable")

    enc_b64 = base64.b64encode(grant.enc_key).decode("ascii")
    out: dict[str, Any] = {"encK": enc_b64, "ipfsPath": f"/ipfs/{cid}", "capId": cap_id}
    try:
        file_obj: File | None = db.get(File, file_id_bytes)
        if file_obj and file_obj.name:
            out["fileName"] = str(file_obj.name)
    except Exception as e:
        logger.debug("prepare_download: failed reading file name for %s: %s", cap_id, e, exc_info=True)

    try:
        ac = chain.get_access_control()
        to_addr = getattr(ac, "address", None) or Web3.to_checksum_address(ZERO_ADDR)
        call_data = chain.encode_use_once_call(cap_b)
        typed = chain.build_forward_typed_data(from_addr=user.eth_address, to_addr=to_addr, data=call_data, gas=120_000)
        req_name = f"useOnce:{cap_id}:{user.id}"
        req_uuid = uuid.uuid5(uuid.NAMESPACE_URL, req_name)
        out.update({"requestId": str(req_uuid), "typedData": typed})
    except Exception as e:
        logger.debug("prepare_download: failed to build typedData for %s: %s", cap_id, e, exc_info=True)
    return out


def _load_one_time_payload(token: str) -> dict[str, Any] | None:
    key = f"dl:once:{token}"
    try:
        try:
            raw = rds.execute_command("GETDEL", key)
        except ResponseError:
            raw = rds.get(key)
            if raw is not None:
                rds.delete(key)
        if not raw:
            return None
        import json as _json

        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode()
        return _json.loads(raw)
    except Exception as e:
        logger.debug("Failed to load one-time payload for %s: %s", token, e, exc_info=True)
        return None


@router.get("/{cap_id}")
def get_download_info(
    cap_id: str,
    # Убираем user=Depends(require_user) и заменяем на зависимость-защитник.
    # Она внутри вызовет get_current_user, проверит PoW и вернет QuotaManager.
    quota_manager: Annotated[QuotaManager, Depends(protect_download)],
    db: Annotated[Session, Depends(get_db)],
    chain: Annotated[Chain, Depends(get_chain)],
) -> dict[str, Any]:
    user = quota_manager.user  # Получаем пользователя из менеджера

    if not (isinstance(cap_id, str) and cap_id.startswith("0x") and len(cap_id) == 66):
        raise HTTPException(400, "bad_cap_id")
    try:
        cap_b = Web3.to_bytes(hexstr=cast(HexStr, cap_id))
    except Exception as e:
        raise HTTPException(400, "bad_cap_id") from e
    grant: Grant | None = db.scalar(select(Grant).where(Grant.cap_id == cap_b))
    if grant is None:
        raise HTTPException(404, "grant_not_found")
    if grant.grantee_id != user.id:
        raise HTTPException(403, "not_grantee")

    file_id_bytes = grant.file_id
    file_hex = "0x" + bytes(file_id_bytes).hex()
    cache_key = f"can_dl:{user.id}:{file_hex}"

    # Quick positive cache to avoid chain calls
    cached = Cache.get_text(cache_key)
    if cached == "1":
        now = datetime.now(UTC)
        # DB-based checks only (fast path)
        revoked = grant.revoked_at is not None or (grant.status == "revoked")
        expired = now > grant.expires_at
        exhausted = int(grant.used or 0) >= int(grant.max_dl or 0)
        if revoked or expired or exhausted:
            # Stale cache → recompute fully
            cached = None
        else:
            # proceed using DB values; chain lookups skipped
            cid = ""
            try:
                cid = chain.cid_of(file_id_bytes) or ""
            except Exception as e:
                logger.debug("get_download_info: chain.cid_of failed for %s: %s", file_hex, e, exc_info=True)
            if not cid:
                f: File | None = db.get(File, file_id_bytes)
                if f and f.cid:
                    cid = f.cid
            if not cid:
                raise HTTPException(502, "registry_unavailable")
            quota_manager.consume_download_bytes(file_id_bytes)
            try:
                file_obj: File | None = db.get(File, file_id_bytes)
                download_size = file_obj.size if file_obj else 0
                event_logger = EventLogger(db)
                event_logger.log_grant_used(
                    cap_id=cap_b,
                    file_id=file_id_bytes,
                    user_id=user.id,
                    download_size=download_size,
                )
            except Exception as e:
                logger.warning("Failed to log grant_used event: %s", e, exc_info=True)

            enc_b64 = base64.b64encode(grant.enc_key).decode("ascii")
            out = {"encK": enc_b64, "ipfsPath": f"/ipfs/{cid}"}
            # Добавим имя файла, если известно
            try:
                file_obj2: File | None = db.get(File, file_id_bytes)
                if file_obj2 and file_obj2.name:
                    out["fileName"] = str(file_obj2.name)
            except Exception as e:
                logger.debug("get_download_info: failed reading file name for %s: %s", file_hex, e, exc_info=True)
            # typedData как было
            try:
                ac = chain.get_access_control()
                to_addr = getattr(ac, "address", None) or Web3.to_checksum_address(ZERO_ADDR)
                call_data = chain.encode_use_once_call(cap_b)
                typed = chain.build_forward_typed_data(
                    from_addr=user.eth_address, to_addr=to_addr, data=call_data, gas=120_000
                )
                import uuid as _uuid

                req_name = f"useOnce:{cap_id}:{user.id}"
                req_uuid = _uuid.uuid5(_uuid.NAMESPACE_URL, req_name)
                out.update({"requestId": str(req_uuid), "typedData": typed})
            except Exception as e:
                logger.debug("get_download_info: failed to build typedData for %s: %s", cap_id, e, exc_info=True)
            _publish_download_event(db, user, cap_id, "download_allowed")
            return out

    # Full recompute path (or cache miss)
    now = datetime.now(UTC)
    revoked = False
    expired = False
    exhausted = False
    try:
        ac = chain.get_access_control()
        g = ac.functions.grants(cap_b).call()
        on_grantee = Web3.to_checksum_address(g[1]) if g and len(g) >= 2 else None
        on_file_id = g[2] if g and len(g) >= 3 else None
        on_expires_at = int(g[3]) if g and len(g) >= 4 else 0
        on_max = int(g[4]) if g and len(g) >= 5 else 0
        on_used = int(g[5]) if g and len(g) >= 6 else 0
        on_revoked = bool(g[7]) if g and len(g) >= 8 else False
        if g and len(g) >= 7 and int(g[6]) == 0:
            raise RuntimeError("not_mined_yet")
        if on_grantee and on_grantee.lower() != user.eth_address.lower():
            raise HTTPException(403, "not_grantee")
        revoked = on_revoked
        expired = now.timestamp() > on_expires_at if on_expires_at else False
        exhausted = on_used >= on_max if on_max else True
        file_id_bytes = bytes(on_file_id) if isinstance(on_file_id, (bytes, bytearray)) else grant.file_id
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("get_download_info: on-chain grants lookup failed for %s: %s", cap_id, e, exc_info=True)
        revoked = grant.revoked_at is not None or (grant.status == "revoked")
        expired = now > grant.expires_at
        exhausted = int(grant.used or 0) >= int(grant.max_dl or 0)
        file_id_bytes = grant.file_id

    if revoked:
        Cache.set_text(cache_key, "0", ttl=10)
        _publish_download_event(db, user, cap_id, "download_denied", reason="revoked")
        raise HTTPException(403, "revoked")
    if expired:
        Cache.set_text(cache_key, "0", ttl=10)
        _publish_download_event(db, user, cap_id, "download_denied", reason="expired")
        raise HTTPException(403, "expired")
    if exhausted:
        Cache.set_text(cache_key, "0", ttl=10)
        _publish_download_event(db, user, cap_id, "download_denied", reason="exhausted")
        raise HTTPException(403, "exhausted")

    # Allowed → set positive cache
    Cache.set_text(cache_key, "1", ttl=10)

    cid = ""
    try:
        cid = chain.cid_of(file_id_bytes) or ""
    except Exception as e:
        logger.debug("get_download_info: chain.cid_of failed for %s: %s", file_id_bytes, e, exc_info=True)
    if not cid:
        f: File | None = db.get(File, file_id_bytes)
        if f and f.cid:
            cid = f.cid
    if not cid:
        _publish_download_event(db, user, cap_id, "download_denied", reason="registry_unavailable")
        raise HTTPException(502, "registry_unavailable")

    # В соответствии с AC: "учитываем useOnce только при успешной выдаче encK"
    quota_manager.consume_download_bytes(file_id_bytes)

    # Готовим deterministic request_id и typedData для useOnce — отдаём клиенту для подписи
    req_name = f"useOnce:{cap_id}:{user.id}"
    req_uuid = uuid.uuid5(uuid.NAMESPACE_URL, req_name)

    typed = None
    try:
        ac = chain.get_access_control()
        to_addr = getattr(ac, "address", None) or Web3.to_checksum_address(ZERO_ADDR)
        call_data = chain.encode_use_once_call(cap_b)
        typed = chain.build_forward_typed_data(from_addr=user.eth_address, to_addr=to_addr, data=call_data, gas=120_000)
    except Exception as e:
        logger.debug("get_download_info: building typedData failed for %s: %s", cap_id, e, exc_info=True)

    # Log grant usage event
    try:
        file_obj: File | None = db.get(File, file_id_bytes)
        download_size = file_obj.size if file_obj else 0
        event_logger = EventLogger(db)
        event_logger.log_grant_used(
            cap_id=cap_b,
            file_id=file_id_bytes,
            user_id=user.id,
            download_size=download_size,
        )
    except Exception as e:
        logger.warning("Failed to log grant_used event: %s", e, exc_info=True)

    enc_b64 = base64.b64encode(grant.enc_key).decode("ascii")
    out = {"encK": enc_b64, "ipfsPath": f"/ipfs/{cid}"}
    try:
        file_obj2: File | None = db.get(File, file_id_bytes)
        if file_obj2 and file_obj2.name:
            out["fileName"] = str(file_obj2.name)
    except Exception as e:
        logger.debug("get_download_info: failed reading file name for full path for %s: %s", file_hex, e, exc_info=True)
    if typed is not None:
        out.update({"requestId": str(req_uuid), "typedData": typed})
    _publish_download_event(db, user, cap_id, "download_allowed")
    return out
