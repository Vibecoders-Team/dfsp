from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import User

router = APIRouter(prefix="/users", tags=["users"])

ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


@router.get("/{addr}/pubkey")
def get_user_pubkey(addr: str, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    if not isinstance(addr, str) or ADDR_RE.fullmatch(addr or "") is None:
        raise HTTPException(400, "bad_eth_address")
    u: User | None = db.query(User).filter(User.eth_address == addr.lower()).one_or_none()
    if u is None:
        raise HTTPException(404, "user_not_found")
    # Публичный ключ не секретный — отдаём как есть
    return {"address": addr, "rsa_public": u.rsa_public, "display_name": u.display_name}
