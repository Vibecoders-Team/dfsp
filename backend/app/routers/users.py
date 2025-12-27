from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import User
from app.security import get_current_user

router = APIRouter(prefix="/users", tags=["users"])

ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
# Simple check for RSA PEM public key format
RSA_PEM_RE = re.compile(r"^-----BEGIN PUBLIC KEY-----\s*[A-Za-z0-9+/=\s]+-----END PUBLIC KEY-----\s*$", re.DOTALL)


class UpdateRsaPublicIn(BaseModel):
    rsa_public: str


@router.get("/{addr}/pubkey")
def get_user_pubkey(addr: str, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    if not isinstance(addr, str) or ADDR_RE.fullmatch(addr or "") is None:
        raise HTTPException(400, "bad_eth_address")
    u: User | None = db.query(User).filter(User.eth_address == addr.lower()).one_or_none()
    if u is None:
        raise HTTPException(404, "user_not_found")
    # Публичный ключ не секретный — отдаём как есть
    return {"address": addr, "rsa_public": u.rsa_public, "display_name": u.display_name}


@router.patch("/me")
def update_profile(
    body: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Update current user's profile (display_name)."""
    if "display_name" in body:
        user.display_name = body["display_name"]
        db.add(user)
        db.commit()
    return {"display_name": user.display_name}


@router.put("/me/rsa-public")
def update_rsa_public(
    body: UpdateRsaPublicIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """
    Update current user's RSA public key.
    This is needed for TON users who need to generate RSA keypair on the client side.
    """
    # Validate that it looks like a valid RSA public key PEM
    if not RSA_PEM_RE.match(body.rsa_public.strip()):
        raise HTTPException(400, "invalid_rsa_public_format")

    user.rsa_public = body.rsa_public.strip()
    db.add(user)
    db.commit()

    return {"ok": True, "address": user.eth_address}

