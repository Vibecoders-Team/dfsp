from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.deps import rds

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Паблишер событий в Redis-очередь.

    Схема сообщения (envelope):

    {
        "event_id": "<uuid или детерминированная строка>",
        "version": 1,
        "type": "grant_created" | "grant_revoked" | "download_allowed" | ...,
        "source": "api",
        "ts": "ISO8601 UTC",
        "subject": {...},   # основные идентификаторы
        "data": {...}       # произвольный payload
    }

    Идемпотентность:
      - event_id используется как логический id.
      - храним его в Redis set `events:seen`.
      - если event_id уже был, второй раз в очередь не кладём.
    """

    def __init__(self, queue_key: str = "events:queue") -> None:
        self.queue_key = queue_key

    def publish(
        self,
        event_type: str,
        *,
        subject: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "api",
        event_id: Optional[str] = None,
        version: int = 1,
    ) -> str:
        eid = event_id or str(uuid.uuid4())

        # --- Идемпотентность по event_id ---
        try:
            # SADD -> 1 если новый, 0 если уже был
            added = rds.sadd("events:seen", eid)
            if added == 0:
                # Уже публиковали такой event_id — молча выходим
                return eid
        except Exception as e:
            logger.warning("EventPublisher: failed to update idempotency set: %s", e)

        envelope = {
            "event_id": eid,
            "version": version,
            "type": event_type,
            "source": source,
            "ts": datetime.now(timezone.utc).isoformat(),
            "subject": subject or {},
            "data": payload or {},
        }

        last_exc: Optional[Exception] = None
        for _attempt in range(3):
            try:
                rds.rpush(self.queue_key, json.dumps(envelope))
                return eid
            except Exception as e:
                last_exc = e

        if last_exc is not None:
            logger.warning(
                "EventPublisher: failed to publish event %s after retries: %s",
                eid,
                last_exc,
            )

        return eid
