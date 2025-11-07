from __future__ import annotations

import os
from typing import Set

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.deps import rds
from app.security import get_current_user
from app.models import User
from app.validators import validate_hex32

router = APIRouter(prefix="/admin", tags=["admin"])


class DenylistIn(BaseModel):
    checksum: str

    @field_validator("checksum")
    @classmethod
    def _v_checksum(cls, v: str) -> str:
        if not validate_hex32(v):
            raise ValueError("bad_checksum")
        return v


def _allowed_admins() -> Set[str]:
    raw = os.getenv("ADMIN_ADDRESSES", "")
    addrs = {a.strip().lower() for a in raw.split(",") if a.strip()}
    return addrs


@router.post("/denylist")
def add_to_denylist(body: DenylistIn, user: User = Depends(get_current_user)) -> dict:
    admins = _allowed_admins()
    if admins and user.eth_address.lower() not in admins:
        raise HTTPException(403, "forbidden")
    try:
        rds.sadd("denylist:checksum", body.checksum)
        return {"ok": True, "checksum": body.checksum}
    except Exception as e:
        raise HTTPException(500, f"redis_error: {e}")

