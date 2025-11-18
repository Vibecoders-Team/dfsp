from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = response.headers
        # Baseline security headers for API
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        # Strict CSP for API responses (no inline, no external sources)
        headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        # Basic anti-XSS (legacy, some old browsers still honor it)
        headers.setdefault("X-XSS-Protection", "1; mode=block")
        # Permissions policy – lock down powerful APIs (tweak if needed for uploads/front-end host separation)
        headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), fullscreen=(), payment=()",
        )
        # Cache-control for API JSON (avoid intermediary caches keeping sensitive data)
        if "application/json" in headers.get("Content-Type", ""):
            headers.setdefault("Cache-Control", "no-store")
        # HSTS only if request already came via HTTPS (reverse proxy sets X-Forwarded-Proto)
        if request.headers.get("X-Forwarded-Proto", "").lower() == "https":
            headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload"
            )
        return response
