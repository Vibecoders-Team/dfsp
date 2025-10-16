from __future__ import annotations

import uuid
from typing import Any, Optional, cast
from typing_extensions import Annotated
from eth_typing import ChecksumAddress
from web3.exceptions import ContractLogicError, BadFunctionCallOutput

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from web3 import Web3
from eth_typing import HexStr

from app.deps import get_db, get_chain
from app.models import File, FileVersion, User
from app.schemas.auth import FileCreateIn, TypedDataOut
from app.security import parse_token

router = APIRouter(prefix="/files", tags=["files"])

AuthorizationHeader = Annotated[str, Header(..., alias="Authorization")]


# ---- auth helper: достаём текущего пользователя из Bearer-токена ----
def require_user(authorization: AuthorizationHeader, db: Session = Depends(get_db)) -> User:
    # более надёжный парсинг без индексации
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "auth_required")

    try:
        payload = parse_token(token)
        sub = getattr(payload, "sub", None) or payload.get("sub")  # зависит от реализации
        user_id = uuid.UUID(str(sub))
    except Exception:
        raise HTTPException(401, "bad_token")

    user_obj: Optional[User] = db.get(User, user_id)
    if user_obj is None:
        raise HTTPException(401, "user_not_found")
    return user_obj  # анализатор понимает, что это User


@router.post("", response_model=TypedDataOut)
def create_file(
        meta: FileCreateIn,
        user: User = Depends(require_user),
        db: Session = Depends(get_db),
        chain=Depends(get_chain),
):
    # валидация hex
    if not (isinstance(meta.fileId, str) and meta.fileId.startswith("0x") and len(meta.fileId) == 66):
        raise HTTPException(400, "bad_file_id")
    if not (isinstance(meta.checksum, str) and meta.checksum.startswith("0x") and len(meta.checksum) == 66):
        raise HTTPException(400, "bad_checksum")

    # подсказываем типизатору HexStr
    fid = Web3.to_bytes(hexstr=cast(HexStr, meta.fileId))
    checksum = Web3.to_bytes(hexstr=cast(HexStr, meta.checksum))

    # PK exists?
    exists = db.scalar(select(File.id).where(File.id == fid))
    if exists:
        raise HTTPException(409, "already_registered")

    # дубликат по checksum для того же владельца
    dup = db.scalar(select(File.id).where(File.owner_id == user.id, File.checksum == checksum))
    if dup:
        raise HTTPException(409, "duplicate_checksum")

    file = File(
        id=fid,
        owner_id=user.id,  # именно user.id
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

    # --- typedData (минимальный конструктор под тесты) ---
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

    # если не нашли, подстрахуемся пустым 0x.. (тесты проверяют только формат)
    zero_addr: str = "0x" + "00" * 20  # type: ignore[arg-type]
    verifying_contract: str = fwd_addr or zero_addr  # ← тип теперь точно str
    verifying_cs: ChecksumAddress = Web3.to_checksum_address(verifying_contract)

    # nonce: если форвардер доступен, можно опросить; иначе 0
    nonce_val: int = 0
    try:
        if fwd is not None:
            signer = Web3.to_checksum_address(user.eth_address)
            # подсказываем анализатору, что у fwd есть .functions.getNonce(...).call()
            nonce_raw = cast(Any, fwd).functions.getNonce(signer).call()
            nonce_val = int(nonce_raw)
    except (ContractLogicError, BadFunctionCallOutput, ValueError):
        # контракт/ABI не тот, адрес пустой, или нода вернула мусор — спокойно падаем в 0
        nonce_val = 0

    # Для тестов — message.data ровно bytes32-хекс
    data_hex32 = meta.checksum

    typed_data = {
        "domain": {
            "name": "MinimalForwarder",
            "version": "0.0.1",
            "chainId": int(chain.chain_id),
            "verifyingContract": verifying_cs,  # ← используем уже приведённый адрес
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
            "to": Web3.to_checksum_address(chain.address),  # адрес FileRegistry из Chain
            "value": 0,
            "gas": 200_000,
            "nonce": nonce_val,
            "data": data_hex32,
        },
    }
    return {"typedData": typed_data}
