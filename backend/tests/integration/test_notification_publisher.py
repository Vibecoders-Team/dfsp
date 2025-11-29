import json

import pytest

from app.deps import rds
from app.services.notification_publisher import (
    SEEN_SET_KEY,
    STREAM_KEY,
    NotificationPublisher,
)


def _clear_notifications() -> None:
    rds.delete(STREAM_KEY)
    rds.delete(SEEN_SET_KEY)


def test_notification_publisher_idempotent() -> None:
    _clear_notifications()
    pub = NotificationPublisher()
    event_id = "test-notify-1"

    for _ in range(2):
        pub.publish(
            "grant_created",
            chat_id=123,
            payload={"capId": "0xabc"},
            event_id=event_id,
        )

    entries = list(rds.xrange(STREAM_KEY))
    assert len(entries) == 1
    _id, raw_fields = entries[0]
    fields = {
        (k.decode() if isinstance(k, (bytes, bytearray)) else k): (
            v.decode() if isinstance(v, (bytes, bytearray)) else v
        )
        for k, v in raw_fields.items()
    }
    assert fields["id"] == event_id
    assert fields["type"] == "grant_created"
    payload = json.loads(fields["payload"])
    assert payload["capId"] == "0xabc"


def test_notification_publisher_requires_chat_id() -> None:
    _clear_notifications()
    pub = NotificationPublisher()

    with pytest.raises(ValueError):
        pub.publish("grant_created", chat_id=0, payload={})
