from __future__ import annotations

import uuid
from typing import Optional, cast, Literal

from eth_typing import HexStr
from fastapi import APIRouter, Depends, Header, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing_extensions import Annotated
from web3 import Web3

from app.deps import get_db, get_chain, rds
from app.models import Grant, User, File
from app.models.meta_tx_requests import MetaTxRequest
from app.security import parse_token
from app.relayer import enqueue_forward_request

router = APIRouter(prefix="/grants", tags=["grants"])

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


@router.get("")
def list_my_grants(
    role: Literal["received", "granted"] = Query("received"),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    chain=Depends(get_chain),
):
    """
    Список грантов для текущего пользователя.
    role=received — я получатель (grantee)
    role=granted  — я выдавший (grantor)
    Возвращает items: [{ fileId, capId, grantor, grantee, maxDownloads, usedDownloads, status, expiresAt, fileName? }]
    """
    if role == "received":
        rows = db.execute(
            select(Grant, File.name)
            .join(File, File.id == Grant.file_id)
            .where(Grant.grantee_id == user.id)
            .order_by(Grant.created_at.desc())
        ).all()
    else:
        rows = db.execute(
            select(Grant, File.name)
            .join(File, File.id == Grant.file_id)
            .where(Grant.grantor_id == user.id)
            .order_by(Grant.created_at.desc())
        ).all()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    items = []
    try:
        ac = chain.get_access_control()
    except Exception:
        ac = None

    for g, file_name in rows:
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
                pass
        else:
            if g.revoked_at is not None:
                status = "revoked"
            elif now > g.expires_at:
                status = "expired"
            elif int(g.used or 0) >= int(g.max_dl or 0):
                status = "exhausted"

        items.append({
            "fileId": "0x" + bytes(g.file_id).hex(),
            "capId": cap_hex,
            "grantor": str(g.grantor_id),
            "grantee": str(g.grantee_id),
            "maxDownloads": max_dl,
            "usedDownloads": used,
            "status": status,
            "expiresAt": expires_at_iso,
            "fileName": file_name,
        })

    return {"items": items}


@router.post("/{cap_id}/revoke")
def revoke_grant(
        cap_id: str,
        response: Response,
        user: User = Depends(require_user),
        db: Session = Depends(get_db),
        chain=Depends(get_chain),
):
    # Validate capId format
    if not (isinstance(cap_id, str) and cap_id.startswith("0x") and len(cap_id) == 66):
        raise HTTPException(400, "bad_cap_id")
    try:
        cap_b = Web3.to_bytes(hexstr=cast(HexStr, cap_id))
    except Exception:
        raise HTTPException(400, "bad_cap_id")

    # Lookup grant by capId
    grant: Optional[Grant] = db.scalar(select(Grant).where(Grant.cap_id == cap_b))
    if grant is None:
        raise HTTPException(404, "grant_not_found")

    # Only grantor can revoke
    if grant.grantor_id != user.id:
        raise HTTPException(403, "not_grantor")

    # Deterministic request_id for idempotency
    req_name = f"revoke:{cap_id}:{user.id}"
    req_uuid = uuid.uuid5(uuid.NAMESPACE_URL, req_name)

    # Build typed data for revoke; return to client for signing
    try:
        ac = chain.get_access_control()
        to_addr = getattr(ac, "address", None) or Web3.to_checksum_address("0x" + "00" * 20)
        call_data = chain.encode_revoke_call(cap_b)
        typed = chain.build_forward_typed_data(from_addr=user.eth_address, to_addr=to_addr, data=call_data, gas=120_000)
    except Exception as e:
        raise HTTPException(502, f"chain_unavailable: {e}")

    response.status_code = 200
    return {"status": "prepared", "requestId": str(req_uuid), "typedData": typed}


@router.get("/{cap_id}")
def get_grant_status(
        cap_id: str,
        user: User = Depends(require_user),
        db: Session = Depends(get_db),
        chain=Depends(get_chain),
):
    if not (isinstance(cap_id, str) and cap_id.startswith("0x") and len(cap_id) == 66):
        raise HTTPException(400, "bad_cap_id")
    try:
        cap_b = Web3.to_bytes(hexstr=cast(HexStr, cap_id))
    except Exception:
        raise HTTPException(400, "bad_cap_id")

    grant: Optional[Grant] = db.scalar(select(Grant).where(Grant.cap_id == cap_b))
    if grant is None:
        raise HTTPException(404, "grant_not_found")

    # allow only grantor or grantee to view
    if grant.grantor_id != user.id and grant.grantee_id != user.id:
        raise HTTPException(403, "forbidden")

    # Build status (prefer on-chain if available)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    status = (grant.status or "pending").lower()
    used = int(grant.used or 0)
    max_dl = int(grant.max_dl)
    expires_at_iso = grant.expires_at.isoformat()

    try:
        ac = chain.get_access_control()
        g = ac.functions.grants(cap_b).call()
        on_grantor = Web3.to_checksum_address(g[0]) if g and len(g) >= 1 else None
        on_grantee = Web3.to_checksum_address(g[1]) if g and len(g) >= 2 else None
        on_expires_at = int(g[3]) if g and len(g) >= 4 else 0
        on_max = int(g[4]) if g and len(g) >= 5 else 0
        on_used = int(g[5]) if g and len(g) >= 6 else 0
        on_revoked = bool(g[7]) if g and len(g) >= 8 else False
        # if not created (createdAt == 0), treat as pending
        if g and len(g) >= 7 and int(g[6]) == 0:
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
        # fallback: use DB-derived status
        if grant.revoked_at is not None:
            status = "revoked"
        elif now > grant.expires_at:
            status = "expired"
        elif int(grant.used or 0) >= int(grant.max_dl or 0):
            status = "exhausted"

    return {
        "capId": cap_id,
        "grantee": None,
        "maxDownloads": max_dl,
        "usedDownloads": used,
        "status": status,
        "expiresAt": expires_at_iso,
    }
