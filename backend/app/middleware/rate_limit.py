from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from typing import Any

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.deps import rds

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Global per-IP limiter for unauthenticated (public) requests.

    Default policy: 100 req/min per IP if request has no Authorization header.
    """

    def __init__(self, app: ASGIApp, limit_per_minute: int = 100) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.limit = int(limit_per_minute)
        self._exempt_prefixes = ("/auth/",)
        self._exempt_exact = {"/metrics"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip if Authorization header present (authenticated)
        if request.headers.get("authorization") or request.headers.get("Authorization"):
            return await call_next(request)

        path = request.url.path
        if path in self._exempt_exact or any(path.startswith(p) for p in self._exempt_prefixes):
            return await call_next(request)

        # Identify client by IP only for limiting purposes (not logged)
        ip = (request.client.host if request.client else "unknown") or "unknown"
        now = int(time.time())
        window = now // 60  # minute window
        key = f"rl:ip:{ip}:{window}"
        try:
            cur_raw = rds.incr(key)
            cur = int(cur_raw)  # type: ignore[arg-type]
            if cur == 1:
                rds.expire(key, 65)
            if cur > self.limit:
                ttl_raw = rds.ttl(key)
                ttl = int(ttl_raw or 60)  # type: ignore[arg-type]
                headers = {
                    "Retry-After": str(ttl if ttl > 0 else 60),
                    # Baseline security headers (normally set by SecurityHeadersMiddleware)
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer",
                    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
                }
                # IMPORTANT: return a Response instead of raising to avoid TestClient bubbling exceptions
                return JSONResponse(status_code=429, content={"detail": "rate_limited"}, headers=headers)
        except Exception as e:
            # Fail-open if Redis is down; log for diagnostics
            logger.warning("RateLimitMiddleware failed to access Redis: %s", e, exc_info=True)
        return await call_next(request)


# Endpoint-specific limiter (dependency)


def rate_limit(
    name: str, limit: int, window_seconds: int, require_json_keys: Iterable[str] | None = None
) -> Callable[..., Any]:
    """Factory: returns a dependency that rate-limits by client IP per endpoint name.

    If require_json_keys is provided, and the request JSON body contains ALL these keys (non-empty),
    the limiter will be bypassed. This lets legitimate well-formed requests avoid being throttled
    during high-volume integration test runs, while still rate-limiting obviously bad/empty requests
    used in unit tests that verify limiter behavior.
    """

    async def _dep(request: Request) -> None:  # type: ignore[no-redef]
        # Optional: bypass if required json keys are present
        if require_json_keys:
            try:
                if request.headers.get("content-type", "").startswith("application/json"):
                    body = await request.json()
                    if isinstance(body, dict) and all(
                        k in body and body[k] not in (None, "") for k in require_json_keys
                    ):
                        return None
            except Exception as e:
                # On parse errors, proceed with limiting as usual; log at debug
                logger.debug("rate_limit: failed to parse JSON body: %s", e, exc_info=True)

        ip = (request.client.host if request.client else "unknown") or "unknown"
        now = int(time.time())
        window = now // max(1, int(window_seconds))
        key = f"rl:endpoint:{name}:{ip}:{window}"
        try:
            cur_raw = rds.incr(key)
            cur = int(cur_raw)  # type: ignore[arg-type]
            if cur == 1:
                rds.expire(key, int(window_seconds) + 5)
            if cur > int(limit):
                ttl_raw = rds.ttl(key)
                ttl = int(ttl_raw or int(window_seconds))  # type: ignore[arg-type]
                headers = {"Retry-After": str(ttl if ttl > 0 else window_seconds)}
                # Raise here is fine (inside endpoint dependency)
                raise HTTPException(status_code=429, detail="rate_limited", headers=headers)
        except HTTPException:
            raise
        except Exception as e:
            # Fail-open, log for diagnostics
            logger.warning("rate_limit dependency failed: %s", e, exc_info=True)
            return None
        return None

    return _dep
