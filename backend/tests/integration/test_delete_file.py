import secrets
import uuid
from datetime import UTC, datetime, timedelta

from app.deps import SessionLocal
from app.models import File, Grant
from app.security import parse_token


def _hex32(b: bytes) -> str:
    return "0x" + b.hex()


def test_delete_file_revokes_and_hides(client, make_user):
    owner_addr, headers = make_user()
    token = headers["Authorization"].split(" ", 1)[1]
    payload = parse_token(token)
    owner_id = uuid.UUID(str(payload["sub"]))

    file_id = secrets.token_bytes(32)
    cap_id = secrets.token_bytes(32)

    session = SessionLocal()
    file = File(
        id=file_id,
        owner_id=owner_id,
        name="test.txt",
        size=123,
        mime="text/plain",
        cid="QmTestCid",
        checksum=b"\x00" * 32,
    )
    session.add(file)
    expires_at = datetime.now(UTC) + timedelta(days=1)
    grant = Grant(
        cap_id=cap_id,
        file_id=file_id,
        grantor_id=owner_id,
        grantee_id=owner_id,
        expires_at=expires_at,
        max_dl=1,
        used=0,
        revoked_at=None,
        status="confirmed",
        tx_hash=None,
        confirmed_at=None,
        enc_key=b"enc",
    )
    session.add(grant)
    session.commit()

    resp = client.delete(f"/files/{_hex32(file_id)}", headers=headers)
    assert resp.status_code == 200, resp.text

    session.refresh(file)
    session.refresh(grant)
    assert file.deleted_at is not None
    assert grant.revoked_at is not None
    assert grant.status == "revoked"

    list_resp = client.get("/files", headers=headers)
    assert list_resp.status_code == 200
    ids = [f["id"] for f in list_resp.json()]
    assert _hex32(file_id) not in ids

    resp2 = client.delete(f"/files/{_hex32(file_id)}", headers=headers)
    assert resp2.status_code == 404

    session.close()
