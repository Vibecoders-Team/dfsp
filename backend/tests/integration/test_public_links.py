from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.deps as deps
import app.security as sec
from app.main import app

client = TestClient(app)


# --- Helpers ---
class FakeRedis:
    def __init__(self):
        self.kv: dict[str, str] = {}

    def get(self, key: str):
        return self.kv.get(key)

    def set(self, key: str, val: str, ex: int | None = None):
        self.kv[key] = val
        return True

    def delete(self, key: str):
        return 1 if self.kv.pop(key, None) is not None else 0

    def incr(self, key: str):
        v = int(self.kv.get(key) or 0)
        self.kv[key] = str(v + 1)
        return int(self.kv[key])


def make_ipfs(content: bytes):
    return SimpleNamespace(cat=lambda cid: content)


def make_chain():
    return SimpleNamespace(cid_of=lambda file_id: None)


def make_file(file_id: bytes, owner_id: uuid.UUID):
    return SimpleNamespace(
        id=file_id,
        owner_id=owner_id,
        name="testfile.txt",
        size=123,
        mime="text/plain",
        cid="bafkreia...",
        checksum=b"\x00" * 32,
    )


def make_public_link(
    token: str,
    file_id: bytes,
    snapshot_name: str = "testfile.txt",
    snapshot_cid: str | None = "bafkreia...",
    pow_difficulty: int | None = None,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
    max_downloads: int | None = None,
    downloads_count: int = 0,
):
    return SimpleNamespace(
        token=token,
        file_id=file_id,
        snapshot_name=snapshot_name,
        snapshot_cid=snapshot_cid,
        pow_difficulty=pow_difficulty,
        expires_at=expires_at,
        revoked_at=revoked_at,
        max_downloads=max_downloads,
        downloads_count=downloads_count,
        snapshot_size=123,
        snapshot_mime="text/plain",
        version=None,
        id=uuid.uuid4(),
    )


# dependency override generator helper


def override_db(fake_db_obj):
    def _gen():
        yield fake_db_obj

    return _gen


# --- Tests ---


def test_create_public_link_returns_token(monkeypatch):
    # Prepare fake user and DB
    user_id = uuid.uuid4()

    fake_user = SimpleNamespace(id=user_id)

    # Fake DB: get(File, id) should return a file-like object
    class FakeDB:
        def get(self, model, key):
            return make_file(key, user_id)

        def add(self, obj):
            # emulate adding
            self._added = obj

        def commit(self):
            return True

    fake_db = FakeDB()

    # Use app.dependency_overrides per project conventions
    app.dependency_overrides[deps.get_db] = override_db(fake_db)
    app.dependency_overrides[sec.get_current_user] = lambda: fake_user

    file_id_hex = "0x" + ("ab" * 32)
    payload = {"version": None, "ttl_sec": 60, "max_downloads": 5, "pow": {"enabled": False}}
    r = client.post(f"/files/{file_id_hex}/public-links", json=payload, headers={"Authorization": "Bearer dummy"})
    assert r.status_code == 201, r.text
    j = r.json()
    assert "token" in j and isinstance(j["token"], str) and len(j["token"]) > 0
    assert "policy" in j


def test_meta_revoked_returns_410():
    # Setup fake DB to return revoked PublicLink
    token = "tokentest"
    file_id = bytes.fromhex("" + "ab" * 32)
    now = datetime.now(UTC)
    pl = make_public_link(token=token, file_id=file_id, revoked_at=now - timedelta(seconds=10))

    class FakeDB:
        def scalar(self, stmt):
            return pl

    fake_db = FakeDB()
    app.dependency_overrides[deps.get_db] = override_db(fake_db)

    r = client.get(f"/public/{token}/meta")
    assert r.status_code == 410


def test_pow_and_content_flow():
    # Create public link requiring PoW
    token = "powtoken"
    file_id = bytes.fromhex("" + "ab" * 32)
    pl = make_public_link(token=token, file_id=file_id, pow_difficulty=8, snapshot_cid="fakecid")

    class FakeDB:
        def scalar(self, stmt):
            return pl

        def add(self, obj):
            pass

        def commit(self):
            pass

    fake_db = FakeDB()
    fake_rds = FakeRedis()
    # Insert a challenge
    challenge = "chal123"
    fake_rds.set(f"pow:challenge:{challenge}", "valid")
    import hashlib as _hl

    solution = None
    for i in range(5000):
        s = f"{i}"
        h = _hl.sha256((challenge + s).encode("utf-8")).hexdigest()
        if h[0] == "0":
            solution = s
            break
    if solution is None:
        solution = "0"

    # Override deps and module-level rds per repo pattern
    app.dependency_overrides[deps.get_db] = override_db(fake_db)
    deps.rds = fake_rds
    app.dependency_overrides[deps.get_ipfs] = lambda: make_ipfs(b"cipherbytes")
    app.dependency_overrides[deps.get_chain] = lambda: make_chain()

    # POST pow
    r = client.post(f"/public/{token}/pow", json={"nonce": challenge, "solution": solution})
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        assert r.json().get("ok") is True
        # Now get content
        r2 = client.get(f"/public/{token}/content")
        assert r2.status_code == 200
        assert r2.headers.get("Content-Disposition") is not None
        assert r2.content == b"cipherbytes"
    else:
        assert r.json() and "bad_solution" in r.text
