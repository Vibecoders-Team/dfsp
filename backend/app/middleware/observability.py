from __future__ import annotations

import hashlib
import time
import uuid
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.telemetry.logging import get_logger
from app.telemetry.metrics import api_requests_total, api_request_duration_seconds
from app.security import parse_token


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Generate trace id and bind logger context
        trace_id = uuid.uuid4().hex
        logger = get_logger().bind(trace_id=trace_id)

        # Compute endpoint label (path template if available)
        route = request.scope.get("route")
        endpoint = getattr(route, "path", None) or request.url.path
        method = request.method.upper()

        # Try to derive user_id_hash from JWT sub without DB access
        user_id_hash = None
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            try:
                token = auth.split(" ", 1)[1]
                payload = parse_token(token)
                sub = str(getattr(payload, "sub", None) or payload.get("sub"))
                if sub and sub.lower() != "none":
                    user_id_hash = hashlib.sha256(sub.encode("utf-8")).hexdigest()
            except Exception:
                user_id_hash = None

        # Timing
        t0 = time.perf_counter()
        status_code = 500
        result_str = "error"
        try:
            response = await call_next(request)
            status_code = response.status_code
            result_str = "ok" if status_code < 400 else "error"
            return response
        finally:
            dt = time.perf_counter() - t0
            # Metrics
            try:
                api_requests_total.labels(method=method, endpoint=endpoint, status=str(status_code)).inc()
                api_request_duration_seconds.labels(endpoint=endpoint).observe(dt)
            except Exception:
                pass
            # Structured log (no IP / headers)
            try:
                action = f"{method} {endpoint}"
                logger.info(
                    "request",
                    action=action,
                    duration_ms=round(dt * 1000.0, 3),
                    result=result_str,
                    status=status_code,
                    user_id_hash=user_id_hash,
                )
            except Exception:
                pass

