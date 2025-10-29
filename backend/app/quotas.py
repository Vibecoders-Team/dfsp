from __future__ import annotations

import hashlib
import secrets
from datetime import date, timedelta

import redis
from fastapi import Depends, HTTPException, Header

from app.config import Settings
from app.deps import get_chain, rds, get_settings, get_redis
from app.models import User
from app.security import get_current_user
from app.blockchain.web3_client import Chain


# --- Метрики ---
def _count_rejection(reason: str, redis_client: redis.Redis):
    redis_client.incr(f"metrics:pow_quota_rejections:{reason}")


# --- Основной сервис ---


class QuotaManager:
    # ... (ЭТОТ КЛАСС ОСТАЕТСЯ БЕЗ ИЗМЕНЕНИЙ)
    def __init__(self, user: User, redis_client: redis.Redis, settings: Settings, chain: Chain):
        self.user = user
        self.rds = redis_client
        self.settings = settings
        self.chain = chain
        self._today = date.today().isoformat()

    def consume_meta_tx(self):
        quota_limit = self.settings.quotas_effective.meta_tx_per_day
        key = f"quota:tx:{self.user.id}:{self._today}"
        current_usage = self.rds.get(key)
        if current_usage and int(current_usage) >= quota_limit:
            _count_rejection("meta_tx_quota", self.rds)
            raise HTTPException(status_code=429, detail="meta_tx_quota_exceeded")
        pipe = self.rds.pipeline()
        pipe.incr(key)
        pipe.expire(key, timedelta(hours=24, minutes=5))
        pipe.execute()

    def consume_download_bytes(self, file_id: bytes):
        quota_limit = self.settings.quotas_effective.download_bytes_day
        key = f"quota:dl_bytes:{self.user.id}:{self._today}"
        try:
            meta = self.chain.meta_of_full(file_id)
            file_size = int(meta.get("size", 0))
            if not file_size:
                return
        except Exception:
            return
        current_usage = self.rds.get(key)
        if current_usage and (int(current_usage) + file_size) > quota_limit:
            _count_rejection("download_quota", self.rds)
            raise HTTPException(status_code=429, detail="download_quota_exceeded")
        pipe = self.rds.pipeline()
        pipe.incrby(key, file_size)
        pipe.expire(key, timedelta(hours=24, minutes=5))
        pipe.execute()


class PoWValidator:
    """Сервис для PoW. Теперь это ОБЫЧНЫЙ класс без __call__."""

    def __init__(
        self, redis_client: redis.Redis = Depends(get_redis), settings: Settings = Depends(get_settings)
    ):
        self.rds = redis_client
        self.settings = settings
        self.difficulty = settings.pow_difficulty_base
        self.prefix = "0" * ((self.difficulty + 3) // 4)

    def get_challenge(self) -> dict:
        """Генерирует и сохраняет новый challenge."""
        challenge = secrets.token_hex(16)
        ttl = self.settings.pow_challenge_ttl_seconds
        self.rds.set(f"pow:challenge:{challenge}", "valid", ex=ttl)
        return {"challenge": challenge, "difficulty": self.difficulty, "ttl": ttl}

    def verify_token(self, pow_token: str | None):
        """Проверяет PoW токен. Эту логику мы вынесли из __call__."""
        if not self.settings.pow_enabled:
            return
        if not pow_token:
            _count_rejection("pow_token_missing", self.rds)
            raise HTTPException(status_code=429, detail="pow_token_required")
        try:
            challenge, nonce = pow_token.split(".", 1)
        except ValueError:
            _count_rejection("pow_token_bad_format", self.rds)
            raise HTTPException(status_code=429, detail="pow_token_bad_format")
        key = f"pow:challenge:{challenge}"
        if self.rds.get(key) is None:
            _count_rejection("pow_expired_or_invalid", self.rds)
            raise HTTPException(status_code=429, detail="pow_expired_or_invalid")
        h = hashlib.sha256(f"{challenge}{nonce}".encode()).hexdigest()
        if not h.startswith(self.prefix):
            _count_rejection("pow_incorrect_solution", self.rds)
            raise HTTPException(status_code=429, detail="pow_incorrect_solution")
        if self.rds.delete(key) == 0:
            _count_rejection("pow_reused", self.rds)
            raise HTTPException(status_code=429, detail="pow_reused")


# --- НОВАЯ ФУНКЦИЯ-ЗАВИСИМОСТЬ для проверки ---
def validate_pow_token(
    pow_validator: PoWValidator = Depends(PoWValidator),
    pow_token: str | None = Header(None, alias="X-PoW-Token"),
):
    """Эта зависимость теперь отвечает ТОЛЬКО за проверку токена."""
    pow_validator.verify_token(pow_token)


# --- Фабрики зависимостей (теперь используют новую функцию) ---


def protect_meta_tx(
    user: User = Depends(get_current_user),
    _: None = Depends(validate_pow_token),  # ИСПОЛЬЗУЕМ НОВУЮ ЗАВИСИМОСТЬ
    redis_client: redis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
    chain: Chain = Depends(get_chain),
) -> User:
    manager = QuotaManager(user, redis_client, settings, chain)
    manager.consume_meta_tx()
    return user


def protect_download(
    user: User = Depends(get_current_user),
    _: None = Depends(validate_pow_token),  # ИСПОЛЬЗУЕМ НОВУЮ ЗАВИСИМОСТЬ
    redis_client: redis.Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
    chain: Chain = Depends(get_chain),
) -> QuotaManager:
    return QuotaManager(user, redis_client, settings, chain)