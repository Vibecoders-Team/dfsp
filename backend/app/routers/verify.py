from __future__ import annotations

import logging
from typing import Annotated, cast

from eth_typing import HexStr
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from web3 import Web3

from app.blockchain.web3_client import Chain
from app.deps import get_chain, get_db
from app.models import File
from app.schemas.verify import FileMeta, VerifyOut

log = logging.getLogger(__name__)
router = APIRouter(prefix="/verify", tags=["verify"])


def normalize_checksum(value: object) -> str | None:
    """Приводит чек-сумму в байтах к hex-строке '0x...'."""
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex()
    return None


@router.get("/{file_id_hex}", response_model=VerifyOut)
def verify(
    file_id_hex: str,
    db: Annotated[Session, Depends(get_db)],
    chain: Annotated[Chain, Depends(get_chain)],
) -> VerifyOut:
    # Валидация формата file_id, чтобы вернуть 400 вместо 422
    if not (
        isinstance(file_id_hex, str) and file_id_hex.startswith("0x") and len(file_id_hex) == 66
    ):
        raise HTTPException(status_code=400, detail="bad_file_id")

    file_id_bytes = Web3.to_bytes(hexstr=cast(HexStr, file_id_hex))

    # 1. Получаем данные из локальной базы (off-chain)
    offchain_data: FileMeta | None = None
    db_file = db.scalar(select(File).where(File.id == file_id_bytes))
    if db_file:
        offchain_data = FileMeta(
            cid=db_file.cid,
            checksum=normalize_checksum(db_file.checksum) or "0x",
            size=db_file.size,
            mime=db_file.mime,
            name=db_file.name,
        )

    # 2. Получаем данные из блокчейна (on-chain)
    onchain_data: FileMeta | None = None
    try:
        # Используем meta_of_full для получения всех полей
        raw_onchain_meta = chain.meta_of_full(file_id_bytes)

        # Проверяем, что смарт-контракт вернул непустые данные
        # (обычно возвращает нули для несуществующего id)
        if raw_onchain_meta and any(raw_onchain_meta.values()):
            checksum_hex = normalize_checksum(raw_onchain_meta.get("checksum"))
            if checksum_hex:
                oc_name = (
                    raw_onchain_meta.get("name")
                    if isinstance(raw_onchain_meta.get("name"), str)
                    else None
                )
                onchain_data = FileMeta(
                    cid=raw_onchain_meta.get("cid", ""),
                    checksum=checksum_hex,
                    size=int(raw_onchain_meta.get("size", 0)),
                    mime=raw_onchain_meta.get("mime", None),
                    name=oc_name,
                )
    except Exception as e:
        # Логируем ошибку, но не прерываем выполнение, чтобы можно было сравнить с пустыми данными
        log.warning(f"Failed to fetch on-chain meta for {file_id_hex}: {e}")
        onchain_data = None

    # 3. Сравниваем чек-суммы
    match = False
    if onchain_data and offchain_data:
        match = onchain_data.checksum == offchain_data.checksum

    if not onchain_data and not offchain_data:
        raise HTTPException(status_code=404, detail="file_not_found")

    return VerifyOut(
        onchain=onchain_data,
        offchain=offchain_data,
        match=match,
    )
