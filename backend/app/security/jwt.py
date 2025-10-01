# backend/app/security/jwt.py

from datetime import datetime, timedelta, timezone
from uuid import UUID
from jose import jwt
from ..settings import settings

def create_access_token(subject: UUID) -> str:
    """
    Создаёт Access JWT токен.
    Срок жизни: 15 минут (из настроек).
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TTL_MINUTES)
    to_encode = {
        "exp": expire,
        "sub": str(subject) # 'sub' (subject) в JWT должен быть строкой
    }
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def create_refresh_token(subject: UUID) -> str:
    """
    Создаёт Refresh JWT токен.
    Срок жизни: 7 дней (из настроек).
    """
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TTL_DAYS)
    to_encode = {
        "exp": expire,
        "sub": str(subject)
    }
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt