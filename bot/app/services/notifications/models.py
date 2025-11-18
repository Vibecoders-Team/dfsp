"""Models for notification events."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class NotificationEvent(BaseModel):
    """Event envelope from queue."""

    event_id: str
    version: int
    type: str
    source: str
    ts: str  # ISO8601 UTC
    subject: dict[str, Any]
    data: dict[str, Any]

    def get_timestamp(self) -> datetime:
        """Parse ISO8601 timestamp."""
        return datetime.fromisoformat(self.ts.replace("Z", "+00:00"))


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
