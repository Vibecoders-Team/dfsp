from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings

router = APIRouter()


def _absolute_url(request: Request, path: str) -> str:
    base = os.getenv("TONCONNECT_APP_URL") or os.getenv("PUBLIC_WEB_ORIGIN") or str(request.base_url).rstrip("/")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{base}{path}"


@router.get("/tonconnect-manifest.json")
def tonconnect_manifest(request: Request) -> JSONResponse:
    """
    TonConnect manifest with permissive CORS so wallet hosts (walletbot, tonkeeper) can fetch it.
    """
    base = os.getenv("TONCONNECT_APP_URL") or os.getenv("PUBLIC_WEB_ORIGIN") or str(request.base_url).rstrip("/")
    icon_url = _absolute_url(request, os.getenv("TONCONNECT_ICON_URL") or "/vite.svg")
    terms_url = _absolute_url(request, os.getenv("TONCONNECT_TERMS_URL") or "/terms")
    manifest = {
        "url": base,
        "name": os.getenv("TONCONNECT_APP_NAME") or "DFSP Mini App",
        "iconUrl": icon_url,
        "termsOfUseUrl": terms_url,
    }
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    return JSONResponse(content=manifest, headers=headers)
