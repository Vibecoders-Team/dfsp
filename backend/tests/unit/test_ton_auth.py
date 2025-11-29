import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.routers.auth import TON_CHALLENGE_TTL, _b64decode
from app.routers.auth import _derive_eth_from_ton_pub as derive_eth


def test_b64decode_roundtrip():
    data = base64.b64encode(b"hello").decode()
    assert _b64decode(data) == b"hello"


def test_derive_eth_from_ton_pub_stable():
    pub = b"0" * 32
    addr = derive_eth(pub)
    assert addr.startswith("0x") and len(addr) == 42


def test_ed25519_verify_nonce():
    sk = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization

    pk = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    nonce = b"nonce-123456789012345678901234567890"
    sig = sk.sign(nonce)
    # Should not raise when verifying via public key
    sk.public_key().verify(sig, nonce)
    # Ensure base64 encoding/decoding works with expected length
    nonce_b64 = base64.b64encode(nonce).decode()
    sig_b64 = base64.b64encode(sig).decode()
    pk_b64 = base64.b64encode(pk).decode()
    assert len(_b64decode(nonce_b64)) == len(nonce)
    assert len(_b64decode(sig_b64)) == len(sig)
    assert len(_b64decode(pk_b64)) == len(pk)
    assert TON_CHALLENGE_TTL >= 300 or TON_CHALLENGE_TTL == 300
