import secrets


def test_bot_links_multilink_switch(client, make_user):
    chat_id = int(secrets.randbelow(1_000_000_000) + 1_000_000_000)

    addr1, _ = make_user()
    resp = client.post("/bot/links", headers={"X-TG-Chat-Id": str(chat_id)}, json={"address": addr1})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert len(data["links"]) == 1
    assert data["links"][0]["address"].lower() == addr1.lower()
    assert data["links"][0]["is_active"] is True

    addr2, _ = make_user()
    resp = client.post("/bot/links", headers={"X-TG-Chat-Id": str(chat_id)}, json={"address": addr2})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert len(data["links"]) == 2
    active = [link for link in data["links"] if link["is_active"]]
    assert len(active) == 1
    assert active[0]["address"].lower() == addr1.lower()

    resp = client.post(
        "/bot/links/switch",
        headers={"X-TG-Chat-Id": str(chat_id)},
        json={"address": addr2},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    active = [link for link in data["links"] if link["is_active"]]
    assert len(active) == 1
    assert active[0]["address"].lower() == addr2.lower()

    resp = client.delete(f"/bot/links/{addr2}", headers={"X-TG-Chat-Id": str(chat_id)})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["links"]) == 1
    assert data["links"][0]["address"].lower() == addr1.lower()
    assert data["links"][0]["is_active"] is True
