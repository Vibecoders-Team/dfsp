import uuid


def test_intents_create_and_consume(client):
    body = {"action": "share", "payload": {"fileId": "0x123"}}
    resp = client.post("/intents", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "intent_id" in data and "url" in data and data["ttl"] > 0

    intent_id = data["intent_id"]
    resp2 = client.post(f"/intents/{intent_id}/consume")
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["ok"] is True
    assert data2["action"] == "share"
    assert data2["payload"] == {"fileId": "0x123"}

    resp3 = client.post(f"/intents/{intent_id}/consume")
    assert resp3.status_code == 409


def test_intents_not_found(client):
    fake = uuid.uuid4()
    resp = client.post(f"/intents/{fake}/consume")
    assert resp.status_code == 404
