from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db
from app.models import User

logger = logging.getLogger(__name__)

bearer = HTTPBearer(auto_error=True)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    token = creds.credentials
    # Increased leeway to handle client-server time skew (e.g., different timezone/NTP drift)
    leeway_seconds = getattr(settings, "jwt_leeway_seconds", 600)

    # DEBUG: Log incoming token info
    logger.info(
        "JWT auth attempt, token_len=%d, token_prefix=%s, secret_prefix=%s",
        len(token) if token else 0,
        token[:20] + "..." if token and len(token) > 20 else token,
        settings.jwt_secret[:8] + "..." if settings.jwt_secret else "(none)"
    )

    try:
        # python-jose doesn't support leeway parameter, so we disable exp verification
        # and check it manually with leeway
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={
                "verify_aud": False,
                "verify_exp": False,  # We'll check exp manually with leeway
            },
        )

        # Manual exp check with leeway
        now = int(datetime.now(UTC).timestamp())
        exp = payload.get("exp", 0)
        iat = payload.get("iat", 0)

        # Check if token is expired (with leeway)
        if exp and now > exp + leeway_seconds:
            logger.warning(
                "JWT expired: now=%d exp=%d leeway=%d diff=%d",
                now, exp, leeway_seconds, now - exp
            )
            raise HTTPException(status_code=401, detail="token_expired")

        # Check if token is from the future (iat check with leeway)
        if iat and iat > now + leeway_seconds:
            logger.warning(
                "JWT iat in future: now=%d iat=%d leeway=%d diff=%d",
                now, iat, leeway_seconds, iat - now
            )
            raise HTTPException(status_code=401, detail="token_not_yet_valid")

        logger.info("JWT decode SUCCESS, payload keys: %s, exp_ok=%s, iat_ok=%s",
                    list(payload.keys()), now <= exp + leeway_seconds, iat <= now + leeway_seconds)
    except HTTPException:
        raise
    except Exception as e:
        # Debug: try to decode without verification to see token contents
        try:
            unverified = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
                options={"verify_exp": False, "verify_iat": False, "verify_aud": False}
            )
            now_ts = int(datetime.now(UTC).timestamp())
            iat = unverified.get("iat", 0)
            exp = unverified.get("exp", 0)
            logger.warning(
                "JWT decode FAILED: %s | server_time=%d iat=%d exp=%d iat_diff=%d exp_diff=%d leeway=%d sub=%s",
                str(e), now_ts, iat, exp, now_ts - iat, exp - now_ts, leeway_seconds, unverified.get("sub", "(none)")
            )
        except Exception as parse_err:
            logger.warning("JWT decode FAILED (cannot parse): %s, parse_error: %s", str(e), str(parse_err))
        raise HTTPException(status_code=401, detail="invalid_token") from e

    uid = payload.get("sub") or payload.get("uid") or payload.get("id")
    logger.info("JWT uid extracted: %s (from payload: sub=%s uid=%s id=%s)", uid, payload.get("sub"), payload.get("uid"), payload.get("id"))

    if not uid:
        logger.warning("JWT invalid: uid is empty, payload=%s", payload)
        raise HTTPException(status_code=401, detail="invalid_token")

    # Явная аннотация переменной
    user: User | None = db.get(User, uuid.UUID(str(uid)))
    if user is None:
        logger.warning("JWT invalid: user not found in DB, uid=%s", uid)
        raise HTTPException(status_code=401, detail="user_not_found")

    logger.info("JWT auth SUCCESS, user_id=%s", uid)
    return user


def make_token(sub: str | dict, ttl_min: int) -> str:
    now = datetime.now(UTC)
    payload = sub if isinstance(sub, dict) else {"sub": sub}
    payload["iat"] = int(now.timestamp())
    payload["exp"] = int((now + timedelta(minutes=ttl_min)).timestamp())
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    # DEBUG: log token creation
    logger.info(
        "make_token: sub=%s iat=%d exp=%d ttl_min=%d secret_prefix=%s token_len=%d",
        payload.get("sub", "(dict)"), payload["iat"], payload["exp"], ttl_min,
        settings.jwt_secret[:8] + "..." if settings.jwt_secret else "(none)",
        len(token)
    )
    return token


def parse_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def create_token(payload: dict, expires_delta: timedelta | None = None) -> str:
    """
    Создает JWT с произвольным payload и exp.
    """
    now = datetime.now(UTC)
    payload = dict(payload)
    if "iat" not in payload:
        payload["iat"] = int(now.timestamp())
    if expires_delta:
        payload["exp"] = int((now + expires_delta).timestamp())
    elif "exp" not in payload:
        payload["exp"] = int((now + timedelta(minutes=settings.jwt_access_ttl_minutes)).timestamp())
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
