from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import UUID
from jose import jwt
from ..deps import get_db, rds
from ..models import File, FileVersion, User
from ..schemas.auth import FileCreateIn, TypedDataOut, MetaTxSubmitIn, FileRow
from ..security import parse_token
from ..config import settings
from ..blockchain import encode_register_call, build_forward_typed_data
from web3 import Web3

try:
    from ..blockchain import encode_register_call, build_forward_typed_data
except Exception:
    encode_register_call = None
    build_forward_typed_data = None
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
def create_file(meta: FileCreateIn, access: str = Header(..., alias="Authorization"), db: Session = Depends(get_db)):
    if access.lower().startswith("bearer "): access = access.split(" ", 1)[1]
    user = _auth_user(db, access)

    # валидации (минимальные)
    if not (meta.fileId.startswith("0x") and len(meta.fileId) == 66): raise HTTPException(400, "bad_file_id")
    if not (meta.checksum.startswith("0x") and len(meta.checksum) == 66): raise HTTPException(400, "bad_checksum")

    # deny/unique per owner
    exists = db.execute(
        select(File).where(File.owner_id == user.id, File.checksum == Web3.to_bytes(hexstr=meta.checksum))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "duplicate_checksum")

    file = File(
        id=Web3.to_bytes(hexstr=meta.fileId),
        owner_id=user.id,
        name=meta.name,
        size=meta.size,
        mime=meta.mime,
        cid=meta.cid,
        checksum=Web3.to_bytes(hexstr=meta.checksum),
    )
    db.add(file);
    db.flush()
    ver = FileVersion(file_id=file.id, cid=file.cid, checksum=file.checksum, size=file.size, mime=file.mime)
    db.add(ver);
    db.commit()

    file_registry_addr = _get_file_registry_addr()
    if not file_registry_addr or not (encode_register_call and build_forward_typed_data):
        raise HTTPException(status_code=503, detail="contracts_unavailable")

    data = encode_register_call(
        Web3.to_bytes(hexstr=meta.fileId),
        meta.cid,
        Web3.to_bytes(hexstr=meta.checksum),
        int(meta.size),
        meta.mime,
    )
    typed = build_forward_typed_data(
        from_addr=user.eth_address,
        to_addr=file_registry_addr,
        data=data,
    )
    return {"typedData": typed}
