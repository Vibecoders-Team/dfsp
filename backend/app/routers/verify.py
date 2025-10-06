from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from web3 import Web3
from ..deps import get_db
from ..schemas.auth import VerifyOut
from ..config import settings
from ..blockchain import registry

router = APIRouter(prefix="/verify", tags=["verify"])

@router.get("/{file_id}", response_model=VerifyOut)
def verify(file_id: str, db: Session = Depends(get_db)):
    if not (file_id.startswith("0x") and len(file_id)==66):
        raise HTTPException(400, "bad_file_id")

    on = registry.functions.metaOf(Web3.to_bytes(hexstr=file_id)).call()
    onchain = {
        "owner": on[0],
        "cid": on[1],
        "checksum": Web3.to_hex(on[2]),
        "size": int(on[3]),
        "mime": on[4],
        "createdAt": int(on[5]),
    }
    off = db.execute(
        select(
            # поля наглядно:
        ).select_from
    )
    # простая сверка с локальной таблицей files (по pk)
    from ..models import File
    f = db.get(File, Web3.to_bytes(hexstr=file_id))
    offchain = {}
    match = False
    if f:
        offchain = {"cid": f.cid, "checksum": Web3.to_hex(f.checksum), "size": f.size, "mime": f.mime}
        match = (onchain["cid"] == f.cid) and (onchain["checksum"] == Web3.to_hex(f.checksum)) and (onchain["size"] == f.size) and (onchain["mime"] == f.mime)
    return VerifyOut(onchain=onchain, offchain=offchain, match=match)
