from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.orm import Session
from web3 import Web3

from app.config import settings
from app.deps import get_chain
from app.deps import get_db
from app.models import File, FileVersion, User
from app.schemas.auth import FileCreateIn, TypedDataOut
from app.security import parse_token

router = APIRouter(prefix="/files", tags=["files"])


def _get_file_registry_addr() -> str | None:
    chain = settings.load_chain_config()
    if not chain:
        return None
    return chain.verifyingContracts.get("FileRegistry")


def _auth_user(db: Session, access: str) -> User:
    try:
        payload = parse_token(access)
    except Exception:
        raise HTTPException(401, "invalid_token")
    user = db.get(User, UUID(payload["sub"]))
    if not user:
        raise HTTPException(401, "user_not_found")
    return user


@router.post("", response_model=TypedDataOut)
def create_file(
        meta: FileCreateIn,
        access: str = Header(..., alias="Authorization"),
        db: Session = Depends(get_db),
        chain=Depends(get_chain),
):
    if access.lower().startswith("bearer "): access = access.split(" ", 1)[1]
    user = _auth_user(db, access)

    # валидации (минимальные)
    if not (meta.fileId.startswith("0x") and len(meta.fileId) == 66): raise HTTPException(400, "bad_file_id")
    if not (meta.checksum.startswith("0x") and len(meta.checksum) == 66): raise HTTPException(400, "bad_checksum")

    fid = Web3.to_bytes(hexstr=meta.fileId)
    checksum = Web3.to_bytes(hexstr=meta.checksum)

    exists_pk = db.get(File, fid)
    if exists_pk:
        raise HTTPException(409, "already_registered")

    dup = db.execute(
        select(File).where(File.owner_id == user.id, File.checksum == checksum)
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(409, "duplicate_checksum")

    file = File(
        id=fid,  # PK bytes32
        owner_id=user.id,
        name=meta.name,
        size=meta.size,
        mime=meta.mime,
        cid=meta.cid,
        checksum=checksum,
    )
    db.add(file)
    db.flush()

    ver = FileVersion(
        file_id=file.id,  # bytes32 → FK
        version=1,
        cid=file.cid,
        checksum=file.checksum,
        size=file.size,
        mime=file.mime,
    )
    db.add(ver)
    db.commit()

    file_registry_addr = chain.address  # адрес FileRegistry из Chain
    if not file_registry_addr:
        raise HTTPException(status_code=503, detail="contracts_unavailable")

    data = chain.encode_register_call(
        Web3.to_bytes(hexstr=meta.fileId),
        meta.cid,
        Web3.to_bytes(hexstr=meta.checksum),
        int(meta.size),
        meta.mime,
    )
    typed = chain.build_forward_typed_data(
        from_addr=user.eth_address,
        to_addr=file_registry_addr,
        data=data,
    )
    return {"typedData": typed}
