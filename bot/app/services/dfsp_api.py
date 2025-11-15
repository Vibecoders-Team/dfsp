import httpx
from typing import Any, Optional

from ..config import settings

import httpx
from pydantic import BaseModel


class DFSPClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=str(settings.DFSP_API_URL),
            timeout=10.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    # Пример на будущее
    async def get_health(self) -> Any:
        r = await self._client.get("/health")
        r.raise_for_status()
        return r.json()
    
class BotProfile(BaseModel):
    address: str
    display_name: str | None = None


async def get_bot_profile(chat_id: int) -> Optional[BotProfile]:
    """
    Запрос профиля пользователя у бэкенда по Telegram chat_id.

    GET {DFSP_API_URL}/bot/me
    Header: X-TG-Chat-Id: <chat_id>

    Возвращает BotProfile или None, если чат не залинкован (404).
    """
    # ВАЖНО: без .rstrip — AnyHttpUrl не умеет rstrip
    url = f"{settings.DFSP_API_URL}/bot/me"

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url, headers={"X-TG-Chat-Id": str(chat_id)})

    if resp.status_code == 404:
        # Чат не привязан к кошельку
        return None

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # чтобы логика ошибок была консистентной с остальными вызовами DFSP
        raise ValueError(f"DFSP GET /bot/me failed: {exc}") from exc

    data = resp.json()
    return BotProfile.model_validate(data)