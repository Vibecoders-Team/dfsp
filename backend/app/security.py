import jwt
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db
from app.models import User

JWT_SECRET = os.getenv("JWT_SECRET", "change_me")
bearer = HTTPBearer(auto_error=True)


def get_current_user(
        creds: HTTPAuthorizationCredentials = Depends(bearer),
        db: Session = Depends(get_db),
) -> User:
    token = creds.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(401, "invalid_token")

    uid = payload.get("sub") or payload.get("uid") or payload.get("id")
    if not uid:
        raise HTTPException(401, "invalid_token")

    try:
        user = db.get(User, uuid.UUID(str(uid)))
    except Exception:
        raise HTTPException(401, "invalid_token")

    if not user:
        raise HTTPException(401, "user_not_found")
    return user


def make_token(sub: str, ttl_min: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=ttl_min)).timestamp())}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def parse_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
