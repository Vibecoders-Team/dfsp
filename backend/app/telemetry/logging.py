from __future__ import annotations

import logging
import os
from typing import Any, Mapping

import structlog


def _get_log_level() -> int:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level, logging.INFO)


def init_logging() -> None:
    """Configure structlog + stdlib logging for JSON output without PII.

    Fields to expect in logs: ts, level, trace_id, user_id_hash, action, duration_ms, result, msg.
    """
    # Route stdlib logging through structlog
    logging.basicConfig(level=_get_log_level(), format="%(message)s")

    # Silence access logs that include client IPs
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("gunicorn.access").disabled = True

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="ts"),
            _rename_level_to_lower,
            _drop_unwanted_keys,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(_get_log_level()),
        cache_logger_on_first_use=True,
    )


def _rename_level_to_lower(logger: Any, method_name: str, event_dict: Mapping[str, Any]):
    # stdlib level is added as 'level', ensure lower-case
    level = event_dict.get("level") or event_dict.get("levelname")
    if level:
        event_dict = dict(event_dict)
        event_dict["level"] = str(level).lower()
        event_dict.pop("levelname", None)
    return event_dict


# No IPs or request headers should leak into logs from our middleware
UNWANTED_KEYS = {"client", "client_ip", "headers", "request_headers", "client_addr"}


def _drop_unwanted_keys(logger: Any, method_name: str, event_dict: Mapping[str, Any]):
    if not UNWANTED_KEYS.intersection(event_dict.keys()):
        return event_dict
    clean = {k: v for k, v in event_dict.items() if k not in UNWANTED_KEYS}
    return clean


def get_logger() -> structlog.stdlib.BoundLogger:  # type: ignore[name-defined]
    return structlog.get_logger()
