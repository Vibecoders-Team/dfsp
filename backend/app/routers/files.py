from __future__ import annotations

import uuid
from typing import Any, Optional, cast, Union
from typing_extensions import Annotated
from eth_typing import ChecksumAddress
from web3.exceptions import ContractLogicError, BadFunctionCallOutput

from fastapi import APIRouter, Depends, Header, HTTPException
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

router = APIRouter(prefix="/files", tags=["files"])

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


@router.post("", response_model=TypedDataOut)
def create_file(
        meta: FileCreateIn,
        user: User = Depends(require_user),
        db: Session = Depends(get_db),
        chain=Depends(get_chain),
):
    if not (isinstance(meta.fileId, str) and meta.fileId.startswith("0x") and len(meta.fileId) == 66):
        raise HTTPException(400, "bad_file_id")
    if not (isinstance(meta.checksum, str) and meta.checksum.startswith("0x") and len(meta.checksum) == 66):
        raise HTTPException(400, "bad_checksum")
    fid = Web3.to_bytes(hexstr=cast(HexStr, meta.fileId))
    checksum = Web3.to_bytes(hexstr=cast(HexStr, meta.checksum))
    exists = db.scalar(select(File.id).where(File.id == fid))
    if exists:
        raise HTTPException(409, "already_registered")
    dup = db.scalar(select(File.id).where(File.owner_id == user.id, File.checksum == checksum))
    if dup:
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
    db.commit()
    fwd: object | None = None
    fwd_addr: Optional[str] = None
    try:
        fwd = chain.contracts.get("MinimalForwarder")
        addr = getattr(fwd, "address", None) if fwd is not None else None
        if isinstance(addr, str):
            fwd_addr = addr
    except Exception:
        fwd = None
        fwd_addr = None
    zero_addr: str = "0x" + "00" * 20
    verifying_contract: str = fwd_addr or zero_addr
    verifying_cs: ChecksumAddress = Web3.to_checksum_address(verifying_contract)
    nonce_val: int = 0
    try:
        if fwd is not None:
            signer = Web3.to_checksum_address(user.eth_address)
            nonce_raw = cast(Any, fwd).functions.getNonce(signer).call()
            nonce_val = int(nonce_raw)
    except (ContractLogicError, BadFunctionCallOutput, ValueError):
        nonce_val = 0
    data_hex32 = meta.checksum
    typed_data = {
        "domain": {
            "name": "MinimalForwarder",
            "version": "0.0.1",
            "chainId": int(chain.chain_id),
            "verifyingContract": verifying_cs,
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
            "to": Web3.to_checksum_address(chain.address),
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
    existing = rds.get(key)
    if isinstance(existing, str) and existing:
        try:
            data = _json.loads(existing)
            capIds = data.get("capIds") or []
        except Exception:
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
        start_nonce = int(ac.functions.grantNonces(grantor_addr).call())
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
    rds.set(key, _json.dumps({"grantor": grantor_addr, "fileId": id, "capIds": cap_ids_hex}), ex=3600, nx=True)
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
    items = [ShareItemOut(grantee=addr_lower_to_input[ga.lower()], capId=ch, status="queued") for (ga, _), ch in zip(grantees, cap_ids_hex)]
    return ShareOut(items=items, typedDataList=typed_list)