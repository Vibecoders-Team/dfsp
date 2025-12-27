import hashlib
import hmac

from app.security_telegram import verify_init_data


def make_init_data(token: str) -> str:
    parts = [
        "auth_date=1700000000",
        "query_id=AAH6sbcYAAAAANewsbcY2kbr",
        'user={"id":12345,"first_name":"John"}',
    ]
    check_str = "\n".join(sorted(parts))
    secret_key = hashlib.sha256(token.encode()).digest()
    good_hash = hmac.new(secret_key, check_str.encode(), hashlib.sha256).hexdigest()
    return "&".join([*parts, f"hash={good_hash}"])


def test_verify_init_data_ok():
    token = "TEST:TOKEN"
    init_data = make_init_data(token)
    res = verify_init_data(init_data, token)
    assert res is not None
    assert res.user_id == 12345


def test_verify_init_data_bad_hash():
    token = "TEST:TOKEN"
    init_data = 'auth_date=1700000000&user={"id":12345}&hash=bad'
    res = verify_init_data(init_data, token)
    assert res is None
