from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from typing import Optional, cast

from eth_typing import HexStr
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing_extensions import Annotated
from web3 import Web3

from app.deps import get_db, get_chain, rds
from app.models import Grant, User, File
from app.models.meta_tx_requests import MetaTxRequest
from app.security import parse_token
from app.relayer import enqueue_forward_request

# --- НОВЫЙ ИМПОРТ ---
from app.quotas import protect_download, QuotaManager
from app.services.event_logger import EventLogger
import logging

router = APIRouter(prefix="/download", tags=["download"])
logger = logging.getLogger(__name__)

# ... (функция require_user остается без изменений)
AuthorizationHeader = Annotated[str, Header(..., alias="Authorization")]


def require_user(authorization: AuthorizationHeader, db: Session = Depends(get_db)) -> User:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "auth_required")
    try:
        payload = parse_token(token)
        sub = getattr(payload, "sub", None) or payload.get("sub")
        user_id = cast("uuid.UUID", uuid.UUID(str(sub)))
    except Exception:
        raise HTTPException(401, "bad_token")
    user_obj: Optional[User] = db.get(User, user_id)
    if user_obj is None:
        raise HTTPException(401, "user_not_found")
    return user_obj


@router.get("/{cap_id}")
def get_download_info(
    cap_id: str,
    # Убираем user=Depends(require_user) и заменяем на зависимость-защитник.
    # Она внутри вызовет get_current_user, проверит PoW и вернет QuotaManager.
    quota_manager: QuotaManager = Depends(protect_download),
    db: Session = Depends(get_db),
    chain=Depends(get_chain),
):
    user = quota_manager.user  # Получаем пользователя из менеджера

    if not (isinstance(cap_id, str) and cap_id.startswith("0x") and len(cap_id) == 66):
        raise HTTPException(400, "bad_cap_id")
    try:
        cap_b = Web3.to_bytes(hexstr=cast(HexStr, cap_id))
    except Exception:
        raise HTTPException(400, "bad_cap_id")
    grant: Optional[Grant] = db.scalar(select(Grant).where(Grant.cap_id == cap_b))
    if grant is None:
        raise HTTPException(404, "grant_not_found")
    if grant.grantee_id != user.id:
        raise HTTPException(403, "not_grantee")
    now = datetime.now(timezone.utc)
    expired = False
    revoked = False
    exhausted = False
    file_id_bytes = grant.file_id
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
        file_id_bytes = (
            bytes(on_file_id) if isinstance(on_file_id, (bytes, bytearray)) else grant.file_id
        )
    except HTTPException:
        raise
    except Exception:
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
    except Exception:
        pass
    if not cid:
        f: Optional[File] = db.get(File, file_id_bytes)
        if f and f.cid:
            cid = f.cid
    if not cid:
        raise HTTPException(502, "registry_unavailable")

    # В соответствии с AC: "учитываем useOnce только при успешной выдаче encK"
    quota_manager.consume_download_bytes(file_id_bytes)

    # Готовим deterministic request_id и typedData для useOnce — отдаём клиенту для подписи
    req_name = f"useOnce:{cap_id}:{user.id}"
    req_uuid = uuid.uuid5(uuid.NAMESPACE_URL, req_name)

    typed = None
    try:
        ac = chain.get_access_control()
        to_addr = getattr(ac, "address", None) or Web3.to_checksum_address("0x" + "00" * 20)
        call_data = chain.encode_use_once_call(cap_b)
        typed = chain.build_forward_typed_data(
            from_addr=user.eth_address, to_addr=to_addr, data=call_data, gas=120_000
        )
    except Exception:
        pass

    # Log grant usage event
    try:
        file_obj: Optional[File] = db.get(File, file_id_bytes)
        download_size = file_obj.size if file_obj else 0
        event_logger = EventLogger(db)
        event_logger.log_grant_used(
            cap_id=cap_b,
            file_id=file_id_bytes,
            user_id=user.id,
            download_size=download_size,
        )
    except Exception as e:
        logger.warning(f"Failed to log grant_used event: {e}")


    enc_b64 = base64.b64encode(grant.enc_key).decode("ascii")
    out = {"encK": enc_b64, "ipfsPath": f"/ipfs/{cid}"}
    if typed is not None:
        out.update({"requestId": str(req_uuid), "typedData": typed})
    return out

