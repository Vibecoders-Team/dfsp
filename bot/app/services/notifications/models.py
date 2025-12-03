"""Models for notification events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Mapping

from pydantic import BaseModel, Field


class NotificationEvent(BaseModel):
    """Event envelope from queue (Redis stream / Rabbit)."""

    id: str = Field(alias="event_id")
    type: str
    chat_id: int
    ts: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "allow"}

    @property
    def event_id(self) -> str:
        return self.id

    def get_timestamp(self) -> datetime:
        """Parse ISO8601 timestamp."""
        if isinstance(self.ts, str):
            return datetime.fromisoformat(self.ts.replace("Z", "+00:00"))
        return self.ts

    @classmethod
    def from_stream_fields(cls, fields: Mapping[str, Any], fallback_id: str | None = None) -> "NotificationEvent":
        """Создает событие из сырого словаря Redis Stream / AMQP."""
        try:
            raw_id = fields.get("id") or fields.get(b"id") or fallback_id
            raw_type = fields.get("type") or fields.get(b"type")
            raw_chat = fields.get("chat_id") or fields.get(b"chat_id")
            raw_ts = fields.get("ts") or fields.get(b"ts") or datetime.now(UTC).isoformat()
            raw_payload = fields.get("payload") or fields.get(b"payload") or "{}"

            def _dec(val: Any) -> Any:
                return val.decode() if isinstance(val, (bytes, bytearray)) else val

            raw_id = _dec(raw_id)
            raw_type = _dec(raw_type)
            raw_chat = _dec(raw_chat)
            raw_ts = _dec(raw_ts)
            raw_payload = _dec(raw_payload)

            payload_dict: dict[str, Any]
            if isinstance(raw_payload, str):
                try:
                    payload_dict = json.loads(raw_payload or "{}")
                except json.JSONDecodeError:
                    payload_dict = {}
            elif isinstance(raw_payload, Mapping):
                payload_dict = dict(raw_payload)
            else:
                payload_dict = {}

            ts_val: datetime
            if isinstance(raw_ts, datetime):
                ts_val = raw_ts
            else:
                raw_ts_str = str(raw_ts)
                if raw_ts_str.endswith("Z"):
                    raw_ts_str = raw_ts_str.replace("Z", "+00:00")
                try:
                    ts_val = datetime.fromisoformat(raw_ts_str)
                except Exception:
                    ts_val = datetime.now(UTC)

            return cls(
                id=str(raw_id),
                type=str(raw_type),
                chat_id=int(raw_chat),
                ts=ts_val,
                payload=payload_dict,
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid notification payload: {fields}") from exc


class NotificationTarget(BaseModel):
    """Target for notification (chat_id + address)."""

    chat_id: int
    address: str


class CoalescedNotification(BaseModel):
    """Coalesced notification (multiple events grouped)."""

    chat_id: int
    event_type: str
    events: list[NotificationEvent]
    first_ts: datetime
    last_ts: datetime
