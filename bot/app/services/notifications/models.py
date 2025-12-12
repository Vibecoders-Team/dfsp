"""Models for notification events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

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
    def from_stream_fields(cls, fields: Mapping[str, Any], fallback_id: str | None = None) -> NotificationEvent:
        """Создает событие из сырого словаря Redis Stream / AMQP."""
        try:

            def _dec(val: Any) -> Any:
                return val.decode() if isinstance(val, (bytes, bytearray)) else val

            decoded_fields: dict[str, Any] = {}
            for k, v in fields.items():
                decoded_fields[_dec(k)] = _dec(v)

            raw_id = decoded_fields.get("id") or fallback_id
            raw_type = decoded_fields.get("type")
            raw_chat = decoded_fields.get("chat_id")
            raw_ts = decoded_fields.get("ts") or datetime.now(UTC).isoformat()
            raw_payload = decoded_fields.get("payload", "{}")

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

            # Забираем все остальные поля и добавляем их в payload, чтобы не терять данные
            reserved_keys = {"id", "type", "chat_id", "ts", "payload"}
            extra_payload = {k: v for k, v in decoded_fields.items() if k not in reserved_keys}
            if extra_payload:
                payload_dict = {**payload_dict, **extra_payload}

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
        except Exception as exc:
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
