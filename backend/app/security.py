from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db
from app.models import User

bearer = HTTPBearer(auto_error=True)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = creds.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_token")

    uid = payload.get("sub") or payload.get("uid") or payload.get("id")
    if not uid:
        raise HTTPException(status_code=401, detail="invalid_token")

    # Явная аннотация переменной
    user: User | None = db.get(User, uuid.UUID(str(uid)))
    if user is None:
        raise HTTPException(status_code=401, detail="user_not_found")
    return user


def make_token(sub: str, ttl_min: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_min)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def parse_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
