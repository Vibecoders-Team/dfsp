from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.deps import rds

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Event publisher to a Redis queue.

    Message schema (envelope):

    {
        "event_id": "<uuid or deterministic string>",
        "version": 1,
        "type": "grant_created" | "grant_revoked" | "download_allowed" | ...,
        "source": "api",
        "ts": "ISO8601 UTC",
        "subject": {...},   # main identifiers
        "data": {...}       # arbitrary payload
    }

    Idempotency:
      - event_id is used as a logical id.
      - we store it in the Redis set `events:seen`.
      - if event_id has already been seen, we don't enqueue it again.
    """

    def __init__(self, queue_key: str = "events:queue") -> None:
        self.queue_key = queue_key

    def publish(
        self,
        event_type: str,
        *,
        subject: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        source: str = "api",
        event_id: str | None = None,
        version: int = 1,
    ) -> str:
        eid = event_id or str(uuid.uuid4())

        # --- Idempotency by event_id ---
        try:
            # SADD -> 1 if new, 0 if already exists
            added = rds.sadd("events:seen", eid)
            if added == 0:
                # This event_id has already been published — exit silently
                return eid
        except Exception as e:
            logger.warning("EventPublisher: failed to update idempotency set: %s", e)

        envelope = {
            "event_id": eid,
            "version": version,
            "type": event_type,
            "source": source,
            "ts": datetime.now(UTC).isoformat(),
            "subject": subject or {},
            "data": payload or {},
        }

        last_exc: Exception | None = None
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
