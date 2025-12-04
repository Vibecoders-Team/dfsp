from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.deps as deps
import app.security as sec
from app.main import app

client = TestClient(app)


def override_db(fake_db_obj):
    def _gen():
        yield fake_db_obj

    return _gen


def make_file(file_id: bytes, owner_id: uuid.UUID):
    return SimpleNamespace(
        id=file_id,
        owner_id=owner_id,
        name="oldname.txt",
        size=42,
        mime="text/plain",
        cid="bafkreia...",
        checksum=b"\x01" * 32,
        created_at=datetime.now(UTC),
    )


def test_owner_can_rename_file():
    user_id = uuid.uuid4()
    fake_user = SimpleNamespace(id=user_id)

    file_id = bytes.fromhex("" + "ab" * 32)
    fake_file = make_file(file_id, user_id)

    class FakeDB:
        def get(self, model, key):
            return fake_file

        def add(self, obj):
            pass

        def commit(self):
            pass

    app.dependency_overrides[deps.get_db] = override_db(FakeDB())
    app.dependency_overrides[sec.get_current_user] = lambda: fake_user

    payload = {"name": "newname.txt"}
    resp = client.patch(f"/files/0x{file_id.hex()}", json=payload, headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200, resp.text
    j = resp.json()
    assert j["name"] == "newname.txt"
    assert j["idHex"] == "0x" + file_id.hex()


def test_non_owner_cannot_rename():
    user_id = uuid.uuid4()
    fake_user = SimpleNamespace(id=user_id)

    file_id = bytes.fromhex("" + "ab" * 32)
    fake_file = make_file(file_id, uuid.uuid4())  # different owner

    class FakeDB:
        def get(self, model, key):
            return fake_file

    app.dependency_overrides[deps.get_db] = override_db(FakeDB())
    app.dependency_overrides[sec.get_current_user] = lambda: fake_user

    payload = {"name": "hacker.txt"}
    resp = client.patch(f"/files/0x{file_id.hex()}", json=payload, headers={"Authorization": "Bearer x"})
    assert resp.status_code == 403


def test_bad_name_returns_400():
    user_id = uuid.uuid4()
    fake_user = SimpleNamespace(id=user_id)

    file_id = bytes.fromhex("" + "ab" * 32)
    fake_file = make_file(file_id, user_id)

    class FakeDB:
        def get(self, model, key):
            return fake_file

    app.dependency_overrides[deps.get_db] = override_db(FakeDB())
    app.dependency_overrides[sec.get_current_user] = lambda: fake_user

    payload = {"name": "   "}
    resp = client.patch(f"/files/0x{file_id.hex()}", json=payload, headers={"Authorization": "Bearer x"})
    assert resp.status_code == 400

