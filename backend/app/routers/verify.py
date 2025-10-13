from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from web3 import Web3

from app.deps import get_db, get_chain
from app.models import File
from app.schemas.auth import VerifyOut

router = APIRouter(prefix="/verify", tags=["verify"])


@router.get("/{file_id}", response_model=VerifyOut)
def verify(file_id: str, db: Session = Depends(get_db), chain=Depends(get_chain)):
    if not (file_id.startswith("0x") and len(file_id) == 66):
        raise HTTPException(400, "bad_file_id")

    fid = Web3.to_bytes(hexstr=file_id)

    on = chain.meta_of_full(fid)
    onchain = {
        "owner": on.get("owner"),
        "cid": on.get("cid"),
        "checksum": on.get("checksum") if isinstance(on.get("checksum"), str) else Web3.to_hex(
            on.get("checksum") or b""),
        "size": int(on.get("size") or 0),
        "mime": on.get("mime"),
        "createdAt": int(on.get("createdAt") or 0),
    }

    f = db.get(File, fid)  # PK=bytes32 — теперь работает напрямую
    offchain = {}
    match = False
    if f:
        offchain = {
            "cid": f.cid,
            "checksum": Web3.to_hex(f.checksum),
            "size": f.size,
            "mime": f.mime,
        }
        match = (
                onchain["cid"] == f.cid and
                onchain["checksum"] == Web3.to_hex(f.checksum) and
                onchain["size"] == f.size and
                onchain["mime"] == f.mime
        )

    return VerifyOut(onchain=onchain, offchain=offchain, match=match)
