import httpx
from typing import Any

from ..config import settings


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
