"""Resolve wallet address to Telegram chat_id."""

import logging
from typing import TYPE_CHECKING

from redis import asyncio as aioredis

if TYPE_CHECKING:
    from .models import NotificationEvent

logger = logging.getLogger(__name__)


class AddressResolver:
    """Resolve wallet address to chat_id with caching."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client
        self.cache_ttl = 3600  # 1 hour

    async def get_chat_id(self, address: str) -> int | None:
        """
        Get chat_id for wallet address.

        Uses Redis cache first, then falls back to backend API lookup.
        """
        if not address:
            return None

        normalized = address.lower()

        # Try cache first
        cache_key = f"addr2chat:{normalized}"
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                return int(cached)
        except Exception as e:
            logger.warning("Failed to read chat_id cache: %s", e)

        # TODO: Query backend API if we add endpoint
        # For now, we'll need to get it from events subject or use a different approach
        # Since backend doesn't expose address -> chat_id API, we'll rely on
        # events containing chat_id or use a reverse lookup mechanism

        return None

    async def cache_chat_id(self, address: str, chat_id: int) -> None:
        """Cache address -> chat_id mapping."""
        if not address or not chat_id:
            return

        normalized = address.lower()
        cache_key = f"addr2chat:{normalized}"

        try:
            await self.redis.setex(cache_key, self.cache_ttl, str(chat_id))
        except Exception as e:
            logger.warning("Failed to cache chat_id: %s", e)

    async def resolve_from_event(self, event: "NotificationEvent") -> int | None:
        """
        Resolve chat_id from event subject.

        Events may contain grantor/grantee/user fields that we can use.
        """
        subject = event.subject or {}

        # For grant events, check grantor and grantee
        grantor = subject.get("grantor")
        grantee = subject.get("grantee")

        # Try grantee first (they receive the notification)
        if grantee:
            chat_id = await self.get_chat_id(str(grantee))
            if chat_id:
                return chat_id

        # Try grantor (they might want to know about revocations)
        if grantor:
            chat_id = await self.get_chat_id(str(grantor))
            if chat_id:
                return chat_id

        # Try user field
        user_addr = subject.get("user")
        if user_addr:
            chat_id = await self.get_chat_id(str(user_addr))
            if chat_id:
                return chat_id

        return None
