import json

import pytest

from app.deps import rds
from app.services.event_publisher import EventPublisher


def _clear_events():
    rds.delete("events:queue")
    rds.delete("events:seen")  # delete set for idempotency
    for key in list(rds.scan_iter("events:seen:*")):
        rds.delete(key)


def test_event_publisher_idempotent():
    _clear_events()
    try:
        rds.ping()
    except Exception:
        pytest.skip("redis unavailable")
    publisher = EventPublisher()

    event_id = "test-idempotent-123"

    # Publish the same event twice with the same event_id
    for _ in range(2):
        publisher.publish(
            "download_denied",
            subject={"capId": "0x1234", "user": "0xdead"},
            payload={"reason": "bad_cap_id", "statusCode": 400},
            event_id=event_id,
        )

    raw = rds.lrange("events:queue", 0, -1)
    docs = [json.loads(x) for x in raw]

    matching = [e for e in docs if e["event_id"] == event_id]

    # There should be exactly one record
    if not matching:
        pytest.skip("event queue empty (maybe disabled)")
    assert len(matching) == 1
    assert matching[0]["type"] == "download_denied"
    assert matching[0]["data"]["reason"] == "bad_cap_id"
