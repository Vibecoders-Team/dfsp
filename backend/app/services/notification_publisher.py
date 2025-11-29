from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.deps import rds

logger = logging.getLogger(__name__)

STREAM_KEY = "tg.notifications"
SEEN_SET_KEY = "tg.notifications:seen"


class NotificationPublisher:
    """Publishes Telegram notification events to Redis stream with idempotency."""

    def __init__(self, stream_key: str = STREAM_KEY) -> None:
        self.stream_key = stream_key

    def publish(
        self,
        event_type: str,
        *,
        chat_id: int,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
        ts: datetime | None = None,
    ) -> str:
        """
        Publish a notification event.

        Envelope (Redis stream fields):
        - id: uuid
        - type: grant_created | grant_received | grant_revoked | download_allowed | download_denied | relayer_warn | ...
        - chat_id: int
        - payload: JSON string
        - ts: ISO timestamp
        """
        if not chat_id:
            raise ValueError("chat_id is required")

        eid = event_id or str(uuid.uuid4())
        ts_iso = (ts or datetime.now(UTC)).isoformat()

        # Idempotency: skip if already published
        try:
            added = rds.sadd(SEEN_SET_KEY, eid)
            if added == 0:
                return eid
        except Exception as e:
            logger.warning("NotificationPublisher: failed to update seen set: %s", e)

        fields = {
            "id": eid,
            "type": event_type,
            "chat_id": str(chat_id),
            "ts": ts_iso,
            "payload": json.dumps(payload or {}, separators=(",", ":")),
        }

        last_exc: Exception | None = None
        for _ in range(3):
            try:
                rds.xadd(self.stream_key, fields)  # type: ignore[arg-type]
                return eid
            except Exception as e:
                last_exc = e

        if last_exc:
            logger.warning("NotificationPublisher: failed to publish %s: %s", eid, last_exc)
        return eid
