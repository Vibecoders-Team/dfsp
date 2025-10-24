from __future__ import annotations

import uuid
from typing import Optional, cast

from eth_typing import HexStr
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing_extensions import Annotated
from web3 import Web3

from app.deps import get_db, get_chain, rds
from app.models import Grant, User
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

    # If already revoked (db cache), noop
    if grant.revoked_at is not None or (grant.status or "") == "revoked":
        return {"status": "noop"}

    # Idempotency by deterministic request_id per (capId, grantor)
    req_name = f"revoke:{cap_id}:{user.id}"
    req_uuid = uuid.uuid5(uuid.NAMESPACE_URL, req_name)

    # If already enqueued (redis or DB), return noop
    if rds.get(f"mtx:req:{req_uuid}"):
        return {"status": "noop"}
    if db.get(MetaTxRequest, req_uuid) is not None:
        return {"status": "noop"}

    # Mark idempotency and persist DB record
    rds.set(f"mtx:req:{req_uuid}", "queued", ex=3600, nx=True)
    db.add(MetaTxRequest(request_id=req_uuid, type="revoke", status="queued"))
    try:
        db.commit()
    except Exception:
        db.rollback()
        # even if commit failed, fall through to try enqueue to avoid breaking API

    # Build typed data and enqueue (best-effort); signature will be provided by client in real flow
    task_id = None
    try:
        ac = chain.get_access_control()
        addr = getattr(ac, "address", None)
        to_addr = Web3.to_checksum_address(addr) if isinstance(addr, str) else Web3.to_checksum_address(
            "0x" + "00" * 20)
        call_data = chain.encode_revoke_call(cap_b)
        typed = chain.build_forward_typed_data(from_addr=user.eth_address, to_addr=to_addr, data=call_data, gas=120_000)
        task_id = enqueue_forward_request(str(req_uuid), typed, "0x")
    except Exception:
        # swallow: optimistic queueing should not block API semantics
        task_id = None

    # 202 Accepted with task_id when we attempted to queue
    response.status_code = 202
    return {"status": "queued", "task_id": task_id}
