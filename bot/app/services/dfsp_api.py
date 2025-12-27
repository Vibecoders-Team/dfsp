from typing import Any

import httpx
from pydantic import BaseModel

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


class BotProfile(BaseModel):
    address: str
    display_name: str | None = None


class BotLink(BaseModel):
    """Одна привязка кошелька к чату."""

    address: str
    is_active: bool


class BotFile(BaseModel):
    """Файл из ответа /bot/files."""

    id_hex: str
    name: str
    size: int
    mime: str
    cid: str
    updatedAt: str  # ISO 8601 datetime string


class BotFileListResponse(BaseModel):
    """Ответ со списком файлов."""

    files: list[BotFile]
    cursor: str | None = None


async def get_bot_files(chat_id: int, limit: int = 10, cursor: str | None = None) -> BotFileListResponse:
    """
    Получить список файлов пользователя.

    GET {DFSP_API_URL}/bot/files
    Headers: X-TG-Chat-Id
    Query: limit, cursor
    """
    api_url = str(settings.DFSP_API_URL).rstrip("/")
    url = f"{api_url}/bot/files"
    params: dict[str, Any] = {"limit": limit}
    if cursor:
        params["cursor"] = cursor

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            url,
            headers={"X-TG-Chat-Id": str(chat_id)},
            params=params,
        )

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"DFSP GET /bot/files failed: {exc}") from exc

    data = resp.json()
    return BotFileListResponse.model_validate(data)


async def get_bot_profile(chat_id: int) -> BotProfile | None:
    """
    Запрос профиля пользователя у бэкенда по Telegram chat_id.

    GET {DFSP_API_URL}/bot/me
    Header: X-TG-Chat-Id: <chat_id>

    Возвращает BotProfile или None, если чат не залинкован (404).
    """
    # Убираем завершающий слеш из URL, если он есть
    api_url = str(settings.DFSP_API_URL).rstrip("/")
    url = f"{api_url}/bot/me"

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


async def get_bot_links(chat_id: int) -> list[BotLink] | None:
    """
    Получить список всех привязанных адресов и активный.

    GET {DFSP_API_URL}/bot/links
    Headers: X-TG-Chat-Id, Authorization: Bearer <DFSP_API_TOKEN>
    """
    api_url = str(settings.DFSP_API_URL).rstrip("/")
    url = f"{api_url}/bot/links"
    headers = {"X-TG-Chat-Id": str(chat_id)}
    if settings.DFSP_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.DFSP_API_TOKEN}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code == 404:
        return None

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"DFSP GET /bot/links failed: {exc}") from exc

    data = resp.json()
    links = data.get("links") or []
    return [BotLink.model_validate(item) for item in links]


async def switch_bot_link(chat_id: int, address: str) -> bool:
    """
    Переключить активный адрес на указанный.

    POST {DFSP_API_URL}/bot/links/switch
    Body: { "address": "0x..." }
    Headers: X-TG-Chat-Id, Authorization
    """
    api_url = str(settings.DFSP_API_URL).rstrip("/")
    url = f"{api_url}/bot/links/switch"
    headers = {"X-TG-Chat-Id": str(chat_id)}
    if settings.DFSP_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.DFSP_API_TOKEN}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(url, json={"address": address}, headers=headers)

    if resp.status_code == 404:
        return False

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"DFSP POST /bot/links/switch failed: {exc}") from exc

    return True


class PrepareDownloadResponse(BaseModel):
    """Ответ от /bot/prepare-download."""

    url: str
    ttl: int
    fileName: str | None = None


async def prepare_download(chat_id: int, cap_id: str) -> PrepareDownloadResponse:
    """
    Запрос одноразовой ссылки для скачивания файла.

    POST {DFSP_API_URL}/bot/prepare-download
    Header: X-TG-Chat-Id: <chat_id>
    Body: {"capId": "0x..."}

    Возвращает PrepareDownloadResponse с одноразовой ссылкой.
    """
    api_url = str(settings.DFSP_API_URL).rstrip("/")
    url = f"{api_url}/bot/prepare-download"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            url,
            headers={"X-TG-Chat-Id": str(chat_id)},
            json={"capId": cap_id},
        )

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"DFSP POST /bot/prepare-download failed: {exc}") from exc

    data = resp.json()
    return PrepareDownloadResponse.model_validate(data)
