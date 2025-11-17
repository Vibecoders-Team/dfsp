from __future__ import annotations

import logging
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from prometheus_client import (  # type: ignore[reportMissingImports]
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import get_db, rds

logger = logging.getLogger(__name__)

# In-process API metrics
api_requests_total = Counter(
    "api_requests_total", "Total API requests", ["method", "endpoint", "status"]
)
api_request_duration_seconds = Histogram(
    "api_request_duration_seconds", "API request duration seconds", ["endpoint"]
)

# Gauges that are set on scrape based on Redis/DB
relayer_queue_length = Gauge("relayer_queue_length", "Relayer queue length", ["queue"])
active_grants_total = Gauge("active_grants_total", "Active grants total")
active_users_total = Gauge("active_users_total", "Active users total")
meta_tx_total = Gauge("meta_tx_total", "Meta-tx total by status", ["status"])
meta_tx_confirmation_seconds_p50 = Gauge(
    "meta_tx_confirmation_seconds_p50", "Relayer confirmation p50 (derived from recent)"
)
meta_tx_confirmation_seconds_p95 = Gauge(
    "meta_tx_confirmation_seconds_p95", "Relayer confirmation p95 (derived from recent)"
)
pow_challenges_total = Gauge("pow_challenges_total", "PoW challenges issued total")
pow_verifications_total = Gauge(
    "pow_verifications_total", "PoW verifications total by status", ["status"]
)
quota_exceeded_total = Gauge("quota_exceeded_total", "Quota exceeded total by type", ["type"])

router = APIRouter()


def _parse_int(x: object) -> int:
    try:
        if x is None:
            return 0
        if isinstance(x, bytes):
            x = x.decode()
        return int(x)
    except Exception:
        logger.debug("_parse_int failed to convert %r", x, exc_info=True)
        return 0


@router.get("/metrics")
def metrics(db: Annotated[Session, Depends(get_db)]) -> PlainTextResponse:
    """Prometheus metrics endpoint.

    Before rendering, pull selected gauges from Redis/DB to current values.
    """
    # Relayer queues (Redis list lengths)
    try:
        for q in ("relayer.high", "relayer.default"):
            try:
                ln = rds.llen(q)  # type: ignore[attr-defined]
                relayer_queue_length.labels(queue=q).set(_parse_int(ln))
            except Exception as e:
                logger.debug("metrics: failed to read redis list len for %s: %s", q, e, exc_info=True)
    except Exception as e:
        logger.warning("metrics: unexpected error while populating relayer queue gauges: %s", e, exc_info=True)

    # Active users / grants DB counters
    try:
        users = db.execute(text("select count(1) from users")).scalar() or 0
        active_users_total.set(int(users))
    except Exception as e:
        logger.warning("metrics: failed to fetch active users count: %s", e, exc_info=True)
    try:
        grants_res = db.execute(text("select count(1) from grants where revoked_at is null"))
        cnt = grants_res.scalar() or 0
        active_grants_total.set(int(cnt))
    except Exception as e:
        logger.warning("metrics: failed to fetch active grants count: %s", e, exc_info=True)

    # Relayer totals and durations from Redis keys populated by relayer
    try:
        success = _parse_int(rds.get("metrics:relayer:success_total"))  # type: ignore[attr-defined]
        error = _parse_int(rds.get("metrics:relayer:error_total"))  # type: ignore[attr-defined]
        meta_tx_total.labels(status="success").set(success)
        # For compatibility we expose both 'error' and 'failure' with the same value
        meta_tx_total.labels(status="error").set(error)
        meta_tx_total.labels(status="failure").set(error)

        raw_any = rds.lrange("metrics:relayer:durations:submit_forward", 0, 199) or []  # type: ignore[attr-defined]
        raw_list = cast(list[Any], list(raw_any))
        vals: list[float] = []

        for x in raw_list:
            try:
                raw = x.decode() if isinstance(x, bytes) else x
                vals.append(float(raw) / 1000.0)  # ms → seconds
            except (UnicodeDecodeError, ValueError, TypeError) as e:
                logger.debug("metrics: skip value %r: %s", x, e, exc_info=True)
                # нет continue — просто идём к следующему элементу
                # (после except в теле цикла всё равно больше кода нет)

        if vals:
            vals_sorted = sorted(vals)
            n = len(vals_sorted)

            def pct(p: float) -> float:
                if n == 0:
                    return 0.0
                k = (n - 1) * p
                f = int(k)
                c = min(f + 1, n - 1)
                if f == c:
                    return float(vals_sorted[f])
                return float(vals_sorted[f] * (c - k) + vals_sorted[c] * (k - f))

            meta_tx_confirmation_seconds_p50.set(pct(0.5))
            meta_tx_confirmation_seconds_p95.set(pct(0.95))
    except Exception as e:
        logger.warning("metrics: failed to populate relayer metrics: %s", e, exc_info=True)

    # PoW / quotas from Redis
    try:
        pow_challenges_total.set(_parse_int(rds.get("metrics:pow_challenges_total")))  # type: ignore[attr-defined]
    except Exception as e:
        logger.debug("metrics: failed to set pow_challenges_total: %s", e, exc_info=True)
    try:
        ok = _parse_int(rds.get("metrics:pow_verifications_total:ok"))  # type: ignore[attr-defined]
        pow_verifications_total.labels(status="ok").set(ok)
        # Aggregate error statuses prefixed pow_ (compat with quotas.py keys)
        for key in rds.scan_iter(match="metrics:pow_quota_rejections:pow_*"):  # type: ignore[attr-defined]
            name: str | None = None
            try:
                name = key.decode().split(":", 2)[-1]
                val = _parse_int(rds.get(key))  # type: ignore[arg-type]
                pow_verifications_total.labels(status=name).set(val)
            except (UnicodeDecodeError, ValueError, TypeError, AttributeError) as e:
                logger.debug(
                    "metrics: skip malformed pow metric %r (key %r): %s",
                    name or key,
                    key,
                    e,
                    exc_info=True,
                )
                # опять же, без continue — цикл сам идёт дальше
    except Exception as e:
        logger.debug("metrics: failed to populate pow verification metrics: %s", e, exc_info=True)
    try:
        for t in ("meta_tx_quota", "download_quota"):
            quota_exceeded_total.labels(type=t).set(
                _parse_int(rds.get(f"metrics:pow_quota_rejections:{t}"))  # type: ignore[attr-defined]
            )
    except Exception as e:
        logger.debug("metrics: failed to set quota_exceeded_total: %s", e, exc_info=True)

    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
