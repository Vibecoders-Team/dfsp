from __future__ import annotations

import redis
from app.deps import get_redis

import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request # Добавили Request
from sqlalchemy.orm import Session
from fastapi.security import HTTPAuthorizationCredentials # Нужно для ручного создания Creds

from app.cache import Cache
from app.deps import get_db, rds
from app.models import User
from app.repos import telegram_repo
from app.schemas.telegram import (
    OkResponse,
    TgLinkCompleteRequest,
    TgLinkStartRequest,
    TgLinkStartResponse,
)

# --- Константы ---
LINK_TOKEN_TTL_SECONDS = 10 * 60
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW_SECONDS = 60

# --- Создание Роутера ---
router = APIRouter(prefix="/tg", tags=["Telegram"])


# --- Зависимость для Рейт-Лимита по Chat ID ---
async def rate_limit_by_chat_id(
    payload: TgLinkStartRequest, redis_client: redis.Redis = Depends(get_redis)
):
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


# --- Эндпоинт #115 ---
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
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=LINK_TOKEN_TTL_SECONDS)
    return TgLinkStartResponse(
        link_token=link_token,
        expires_at=expires_at,
    )


# --- Эндпоинт #116 ---
@router.post(
    "/link-complete",
    response_model=OkResponse,
    summary="Complete Telegram account linking",
)
async def complete_telegram_link(
        payload: TgLinkCompleteRequest,
        request: Request,
        db: Session = Depends(get_db),
) -> OkResponse:
    # --- Ленивое разрешение get_current_user ---
    from app.security import get_current_user

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    creds = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=auth_header.split(" ")[1]
    )

    try:
        current_user: User = get_current_user(creds=creds, db=db)
    except HTTPException as e:
        raise e
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication token or user")
    # --- Конец ленивого разрешения ---

    cache_key = f"tg:link:{payload.link_token}"
    chat_id_str = Cache.get_text(cache_key)

    if not chat_id_str:
        raise HTTPException(status_code=400, detail="Invalid or expired link_token.")

    Cache.delete(cache_key)

    try:
        chat_id = int(chat_id_str)
        telegram_repo.link_user_to_chat(
            db=db, wallet_address=current_user.eth_address, chat_id=chat_id
        )
    except ValueError:
        raise HTTPException(status_code=500, detail="Invalid chat_id found in cache.")
    except Exception:
        raise HTTPException(status_code=500, detail="Could not save telegram link.")

    return OkResponse()

@router.delete(
    "/link",
    response_model=OkResponse,
    summary="Unlink Telegram account",
)
async def unlink_telegram_account(
    request: Request,
    db: Session = Depends(get_db),
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
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication token or user")

    # Вызываем функцию из репозитория для отзыва ссылок
    try:
        telegram_repo.revoke_links_by_address(db=db, wallet_address=current_user.eth_address)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not revoke telegram links.")

    return OkResponse()