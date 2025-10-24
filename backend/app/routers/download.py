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

router = APIRouter(prefix="/download", tags=["download"])

AuthorizationHeader = Annotated[str, Header(..., alias="Authorization")]


# Copy of helper in files.py to avoid cross-router import cycles
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
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    chain=Depends(get_chain),
):
    # Validate hex-32 manually to return 400 instead of FastAPI's 422
    if not (isinstance(cap_id, str) and cap_id.startswith("0x") and len(cap_id) == 66):
        raise HTTPException(400, "bad_cap_id")

    # Parse capId hex32 → bytes32
    try:
        cap_b = Web3.to_bytes(hexstr=cast(HexStr, cap_id))
    except Exception:
        raise HTTPException(400, "bad_cap_id")

    # Find grant off-chain
    grant: Optional[Grant] = db.scalar(select(Grant).where(Grant.cap_id == cap_b))
    if grant is None:
        raise HTTPException(404, "grant_not_found")

    # Only grantee may request
    if grant.grantee_id != user.id:
        raise HTTPException(403, "not_grantee")

    now = datetime.now(timezone.utc)

    # On-chain verification (preferred), fallback to DB cache
    expired = False
    revoked = False
    exhausted = False
    try:
        ac = chain.get_access_control()
        g = ac.functions.grants(cap_b).call()
        # Solidity Grant tuple: (grantor, grantee, fileId, expiresAt, maxDownloads, used, createdAt, revoked)
        on_grantee = Web3.to_checksum_address(g[1]) if g and len(g) >= 2 else None
        on_file_id = g[2] if g and len(g) >= 3 else None
        on_expires_at = int(g[3]) if g and len(g) >= 4 else 0
        on_max = int(g[4]) if g and len(g) >= 5 else 0
        on_used = int(g[5]) if g and len(g) >= 6 else 0
        on_revoked = bool(g[7]) if g and len(g) >= 8 else False

        # If never existed on-chain: createdAt == 0 → treat as not found
        if g and len(g) >= 7 and int(g[6]) == 0:
            # fallback to DB checks
            raise RuntimeError("not_mined_yet")

        # Verify grantee address matches JWT eth address
        if on_grantee and on_grantee.lower() != user.eth_address.lower():
            raise HTTPException(403, "not_grantee")

        revoked = on_revoked
        expired = now.timestamp() > on_expires_at if on_expires_at else False
        exhausted = on_used >= on_max if on_max else True
        file_id_bytes = bytes(on_file_id) if isinstance(on_file_id, (bytes, bytearray)) else grant.file_id
    except HTTPException:
        # direct passthrough for not_grantee
        raise
    except Exception:
        # Fallback to DB cache if chain unavailable or not yet synced
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

    # Get CID from registry, fallback to DB
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
        # Can't resolve content path
        raise HTTPException(502, "registry_unavailable")

    # Optimistically enqueue useOnce(capId) — persistent deterministic request_id
    req_name = f"useOnce:{cap_id}:{user.id}"
    req_uuid = uuid.uuid5(uuid.NAMESPACE_URL, req_name)
    # idempotent Redis marker (1h TTL)
    rds.set(f"mtx:req:{req_uuid}", "queued", ex=3600, nx=True)
    # DB record for visibility
    existing: Optional[MetaTxRequest] = db.get(MetaTxRequest, req_uuid)
    if existing is None:
        db.add(MetaTxRequest(request_id=req_uuid, type="useOnce", status="queued"))
        try:
            db.commit()
        except Exception:
            db.rollback()

    # Try to enqueue to Celery (best-effort)
    try:
        ac = chain.get_access_control()
        to_addr = getattr(ac, "address", None) or Web3.to_checksum_address("0x" + "00" * 20)
        call_data = chain.encode_use_once_call(cap_b)
        typed = chain.build_forward_typed_data(from_addr=user.eth_address, to_addr=to_addr, data=call_data, gas=120_000)
        # Signature unknown here; enqueue anyway with empty signature so task appears (worker will fail verify)
        enqueue_forward_request(str(req_uuid), typed, "0x")
    except Exception:
        # no-op; it's optimistic and shouldn't block download
        pass

    enc_b64 = base64.b64encode(grant.enc_key).decode("ascii")
    return {"encK": enc_b64, "ipfsPath": f"/ipfs/{cid}"}
