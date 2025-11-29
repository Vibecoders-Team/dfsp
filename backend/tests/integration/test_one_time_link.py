import json

from app.deps import rds


def test_one_time_json_consumes(client):
    token = "test-token-1"
    key = f"dl:once:{token}"
    payload = {"encK": "abc", "ipfsPath": "/ipfs/cid", "fileName": "name"}
    rds.setex(key, 300, json.dumps(payload))

    resp = client.get(f"/dl/one-time/{token}", headers={"accept": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["fileName"] == "name"

    resp2 = client.get(f"/dl/one-time/{token}", headers={"accept": "application/json"})
    assert resp2.status_code == 410


def test_one_time_browser_redirect_does_not_consume(client):
    token = "test-token-2"
    key = f"dl:once:{token}"
    rds.setex(key, 300, json.dumps({"foo": "bar"}))

    resp = client.get(f"/dl/one-time/{token}")
    assert resp.status_code == 302
    assert resp.headers["location"].endswith(f"/dl/one-time/{token}")

    # Now consume
    resp2 = client.get(f"/dl/one-time/{token}", headers={"accept": "application/json"})
    assert resp2.status_code == 200
    resp3 = client.get(f"/dl/one-time/{token}", headers={"accept": "application/json"})
    assert resp3.status_code == 410
