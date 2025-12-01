from __future__ import annotations

import os
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated

import redis
from fastapi import APIRouter, Depends, HTTPException, Request  # Добавили Request
from fastapi.security import HTTPAuthorizationCredentials  # Нужно для ручного создания Creds
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cache import Cache
from app.deps import get_db, get_redis
from app.models import User
from app.repos import telegram_repo
from app.repos import user_repo
from app.schemas.telegram import (
    OkResponse,
    TgLinkCompleteRequest,
    TgLinkStartRequest,
    TgLinkStartResponse,
)
from app.security import create_token
from app.security_telegram import InitData, verify_init_data

# --- Константы ---
LINK_TOKEN_TTL_SECONDS = 10 * 60
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW_SECONDS = 60

# --- Создание Роутера ---
router = APIRouter(prefix="/tg", tags=["Telegram"])


# --- Schemas ---


class WebAppAuthIn(BaseModel):
    initData: str


class WebAppAuthOut(BaseModel):
    session: str
    exp: int


# --- Зависимость для Рейт-Лимита по Chat ID ---
async def rate_limit_by_chat_id(
    payload: TgLinkStartRequest, redis_client: Annotated[redis.Redis, Depends(get_redis)]
) -> None:
    now = int(time.time())
    window = now // RATE_LIMIT_WINDOW_SECONDS
    key = f"rl:tg-link-start:{payload.chat_id}:{window}"

    # Убираем try-except, чтобы видеть ошибки, и используем redis_client
    # В реальном приложении можно вернуть try-except, но с логированием ошибки.
    cur = int(redis_client.incr(key))
    if cur == 1:
        redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS + 5)

    if cur > RATE_LIMIT_REQUESTS:
        ttl = int(redis_client.ttl(key) or RATE_LIMIT_WINDOW_SECONDS)
        headers = {"Retry-After": str(ttl if ttl > 0 else RATE_LIMIT_WINDOW_SECONDS)}
        raise HTTPException(status_code=429, detail="Too many requests", headers=headers)


@router.post(
    "/link-start",
    response_model=TgLinkStartResponse,
    summary="Start Telegram account linking process",
    dependencies=[Depends(rate_limit_by_chat_id)],
)
async def start_telegram_link(payload: TgLinkStartRequest) -> TgLinkStartResponse:
    link_token = secrets.token_urlsafe(32)
    cache_key = f"tg:link:{link_token}"
    Cache.set_text(cache_key, str(payload.chat_id), ttl=LINK_TOKEN_TTL_SECONDS)
    expires_at = datetime.now(UTC) + timedelta(seconds=LINK_TOKEN_TTL_SECONDS)
    return TgLinkStartResponse(
        link_token=link_token,
        expires_at=expires_at,
    )


@router.post("/webapp/auth", response_model=WebAppAuthOut)
def telegram_webapp_auth(body: WebAppAuthIn, db: Annotated[Session, Depends(get_db)]) -> WebAppAuthOut:
    """Validate Telegram initData and issue short-lived webapp session JWT."""
    bot_token = os.getenv("BOT_TOKEN") or ""
    init_data: InitData | None = verify_init_data(body.initData, bot_token=bot_token)
    if init_data is None:
        raise HTTPException(status_code=403, detail="bad_signature")

    chat_id = init_data.user_id
    if chat_id is None:
        raise HTTPException(status_code=403, detail="bad_signature")

    # Resolve linked wallet by chat_id and issue JWT for the linked DFSP user.
    wallet = telegram_repo.get_wallet_by_chat_id(db, chat_id)
    if not wallet:
        raise HTTPException(status_code=403, detail="tg_not_linked")

    user = user_repo.get_by_eth_address(db, wallet)
    if not user:
        raise HTTPException(status_code=403, detail="user_not_found")

    payload = {"sub": str(user.id), "scope": "tg_webapp", "chat_id": chat_id}
    session_jwt = create_token(payload, expires_delta=timedelta(hours=1))
    return WebAppAuthOut(session=session_jwt, exp=3600)


@router.post(
    "/link-complete",
    response_model=OkResponse,
    summary="Complete Telegram account linking",
)
async def complete_telegram_link(
    payload: TgLinkCompleteRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> OkResponse:
    # --- Ленивое разрешение get_current_user ---
    from app.security import get_current_user

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth_header.split(" ")[1])

    try:
        current_user: User = get_current_user(creds=creds, db=db)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication token or user") from exc
    # --- Конец ленивого разрешения ---

    cache_key = f"tg:link:{payload.link_token}"
    chat_id_str = Cache.get_text(cache_key)

    if not chat_id_str:
        raise HTTPException(status_code=400, detail="Invalid or expired link_token.")

    Cache.delete(cache_key)

    try:
        chat_id = int(chat_id_str)
        telegram_repo.link_user_to_chat(db=db, wallet_address=current_user.eth_address, chat_id=chat_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Invalid chat_id found in cache.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not save telegram link.") from exc

    return OkResponse()


@router.delete(
    "/link",
    response_model=OkResponse,
    summary="Unlink Telegram account",
)
async def unlink_telegram_account(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> OkResponse:
    """
    Revokes all active links associated with the authenticated user's wallet address.
    This is an idempotent operation.
    """
    # Используем тот же "ленивый" подход для получения current_user,
    # который не ломает запуск приложения с psycopg.
    from app.security import get_current_user

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth_header.split(" ")[1])

    try:
        current_user: User = get_current_user(creds=creds, db=db)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication token or user") from exc

    # Вызываем функцию из репозитория для отзыва ссылок
    try:
        telegram_repo.revoke_links_by_address(db=db, wallet_address=current_user.eth_address)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not revoke telegram links.") from exc

    return OkResponse()
