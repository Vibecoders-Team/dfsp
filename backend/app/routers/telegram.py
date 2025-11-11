from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.cache import Cache
from app.deps import rds  # Импортируем rds для прямого использования в рейт-лимитере
from app.schemas.telegram import TgLinkStartRequest, TgLinkStartResponse

# --- Константы ---
LINK_TOKEN_TTL_SECONDS = 10 * 60  # 10 минут
RATE_LIMIT_REQUESTS = 5  # 5 запросов
RATE_LIMIT_WINDOW_SECONDS = 60  # в 60 секунд (5 запросов в минуту)

# --- Создание Роутера ---
router = APIRouter(prefix="/tg", tags=["Telegram"])


# --- Зависимость для Рейт-Лимита по Chat ID ---
# Мы создаем свою зависимость, так как стандартная работает по IP, а нам нужен chat_id из тела запроса.
async def rate_limit_by_chat_id(payload: TgLinkStartRequest):
    """Rate-limits requests based on chat_id from the request body."""
    now = int(time.time())
    window = now // RATE_LIMIT_WINDOW_SECONDS

    # Ключ в Redis будет уникальным для каждого chat_id в рамках минутного окна
    key = f"rl:tg-link-start:{payload.chat_id}:{window}"

    try:
        # Увеличиваем счетчик и проверяем его значение
        cur = int(rds.incr(key))

        # Если это первый запрос в этом окне, устанавливаем TTL
        if cur == 1:
            rds.expire(key, RATE_LIMIT_WINDOW_SECONDS + 5)  # +5 секунд запаса

        # Если счетчик превысил лимит, возвращаем ошибку 429
        if cur > RATE_LIMIT_REQUESTS:
            ttl = int(rds.ttl(key) or RATE_LIMIT_WINDOW_SECONDS)
            headers = {"Retry-After": str(ttl if ttl > 0 else RATE_LIMIT_WINDOW_SECONDS)}
            raise HTTPException(status_code=429, detail="Too many requests", headers=headers)

    except Exception:
        # Если Redis недоступен, не блокируем запрос (fail-open)
        pass


# --- Эндпоинт ---
@router.post(
    "/link-start",
    response_model=TgLinkStartResponse,
    summary="Start Telegram account linking process",
    dependencies=[Depends(rate_limit_by_chat_id)],  # Применяем наш рейт-лимитер
)
async def start_telegram_link(payload: TgLinkStartRequest) -> TgLinkStartResponse:
    """
    Generates a single-use, short-lived link_token for a given chat_id.
    This token is then used by the web frontend to complete the linking process.
    """
    # 1. Генерация безопасного токена
    link_token = secrets.token_urlsafe(32)

    # 2. Ключ для хранения в Redis. Префикс "tg:link" для порядка.
    cache_key = f"tg:link:{link_token}"

    # 3. Сохраняем chat_id в Redis, используя наш токен как ключ.
    # Используем готовый класс Cache, который уже есть в проекте.
    Cache.set_text(cache_key, str(payload.chat_id), ttl=LINK_TOKEN_TTL_SECONDS)

    # 4. Вычисляем и возвращаем время истечения токена
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=LINK_TOKEN_TTL_SECONDS)

    return TgLinkStartResponse(
        link_token=link_token,
        expires_at=expires_at,
    )