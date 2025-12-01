from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import uuid as uuidlib
from os import getenv
from typing import Annotated, Any, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_keys.datatypes import Signature
from eth_utils.address import to_canonical_address
from eth_utils.crypto import keccak
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, rds
from app.middleware.rate_limit import rate_limit
from app.models import User
from app.schemas.auth import ChallengeOut, LoginIn, RegisterIn, Tokens
from app.security import make_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_DOMAIN: dict[str, str] = {"name": "DFSP-Login", "version": "1"}
EXPECTED_CHAIN_ID = int(getenv("CHAIN_ID", "0") or 0) or None
TON_CHALLENGE_TTL = 300

# --- Валидаторы (ETH) ---
ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
NONCE_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
SIG_RE = re.compile(r"^0x[0-9a-fA-F]{130}$")


def _require(cond: bool, msg: str) -> None:
    if not cond:
        logger.warning("ETH _require failed: %s", msg)
        raise HTTPException(400, msg)


def _validate_inputs(eth_address: str, nonce_hex: str, signature: str) -> None:
    _require(
        isinstance(eth_address, str) and ADDR_RE.fullmatch(eth_address or "") is not None,
        "bad_eth_address",
    )
    _require(isinstance(nonce_hex, str) and NONCE_RE.fullmatch(nonce_hex or "") is not None, "bad_nonce")
    _require(
        isinstance(signature, str) and SIG_RE.fullmatch(signature or "") is not None,
        "bad_signature_format",
    )


def _left_pad32(b: bytes) -> bytes:
    if len(b) >= 32:
        return b[-32:]
    return (b"\x00" * (32 - len(b))) + b


def _eip712_digest_login(eth_address: str, nonce_hex: str) -> bytes:
    # домен: EIP712Domain(string name,string version)
    typehash_domain = keccak(text="EIP712Domain(string name,string version)")
    name_hash = keccak(text=LOGIN_DOMAIN["name"])
    version_hash = keccak(text=LOGIN_DOMAIN["version"])
    domain_sep = keccak(typehash_domain + name_hash + version_hash)

    # тип: LoginChallenge(address address,bytes32 nonce)
    typehash_login = keccak(text="LoginChallenge(address address,bytes32 nonce)")
    addr_word = _left_pad32(to_canonical_address(eth_address))
    nonce32 = bytes.fromhex(nonce_hex[2:])  # уже проверен форматом
    struct_hash = keccak(typehash_login + addr_word + nonce32)

    return keccak(b"\x19\x01" + domain_sep + struct_hash)


def _verify_login_signature(typed_data: dict[str, Any], signature: str) -> str:
    try:
        msg = encode_typed_data(full_message=typed_data)
    except Exception as e:
        logger.warning("ETH _verify_login_signature: typed_data_invalid: %s", e)
        raise HTTPException(400, f"typed_data_invalid: {e}") from e
    try:
        return Account.recover_message(msg, signature=signature)
    except Exception as e:
        logger.warning("ETH _verify_login_signature: bad_signature: %s", e)
        raise HTTPException(401, f"bad_signature: {e}") from e


def _recover_login_with_nonce(eth_address: str, nonce_hex: str, signature: str) -> str:
    _validate_inputs(eth_address, nonce_hex, signature)
    digest = _eip712_digest_login(eth_address, nonce_hex)

    try:
        sig_bytes = bytes.fromhex(signature[2:])  # 65 байт
        sig = Signature(sig_bytes)
        pub = sig.recover_public_key_from_msg_hash(digest)
        return pub.to_checksum_address()
    except Exception as e:
        logger.warning("ETH _recover_login_with_nonce: bad_signature: %s", e)
        raise HTTPException(401, "bad_signature") from e


def build_login_typed_data(nonce_hex: str, eth_address: str) -> dict[str, Any]:
    return {
        "domain": LOGIN_DOMAIN,
        "types": {
            "LoginChallenge": [
                {"name": "address", "type": "address"},
                {"name": "nonce", "type": "bytes32"},
            ]
        },
        "primaryType": "LoginChallenge",
        "message": {"address": eth_address, "nonce": nonce_hex},
    }


def validate_login_typed_data(td: dict[str, Any], nonce_hex: str, eth_address: str) -> None:
    _require(isinstance(td, dict), "typed_data_invalid")
    domain = td.get("domain")
    types = td.get("types")
    primary = td.get("primaryType")
    message = td.get("message")
    _require(primary == "LoginChallenge", "bad_primary_type")
    _require(isinstance(domain, dict), "bad_domain")
    _require(domain.get("name") == LOGIN_DOMAIN["name"], "bad_domain_name")
    _require(domain.get("version") == LOGIN_DOMAIN["version"], "bad_domain_version")
    if "chainId" in domain and EXPECTED_CHAIN_ID is not None:
        _require(int(domain["chainId"]) == EXPECTED_CHAIN_ID, "bad_domain_chainId")
    _require(isinstance(types, dict), "bad_types")
    lc = types.get("LoginChallenge")
    _require(isinstance(lc, list) and len(lc) == 2, "bad_types_login")
    names = [f.get("name") for f in lc if isinstance(f, dict)]
    types_ = [f.get("type") for f in lc if isinstance(f, dict)]
    _require(names == ["address", "nonce"], "bad_types_fields")
    _require(types_ == ["address", "bytes32"], "bad_types_field_types")
    _require(isinstance(message, dict), "bad_message")
    _require(message.get("address") == eth_address, "bad_message_address")
    _require(message.get("nonce") == nonce_hex, "bad_message_nonce")


@router.post("/challenge", response_model=ChallengeOut)
def challenge() -> ChallengeOut:
    challenge_id = secrets.token_hex(16)
    nonce = "0x" + secrets.token_hex(32)
    exp_sec = 300
    rds.setex(f"auth:chal:{challenge_id}", exp_sec, json.dumps({"nonce": nonce}))
    return ChallengeOut(challenge_id=challenge_id, nonce=nonce, exp_sec=exp_sec)


# ---------- Общие хелперы для TON ----------

def _parse_ton_address(addr: str) -> tuple[int, bytes]:
    """
    Разбираем raw-адрес вида "<workchain>:<hex32>" → (wc, hash32).
    Пример: "0:348bcf82..."
    """
    try:
        wc_str, hash_hex = addr.split(":", 1)
        wc = int(wc_str)
        h = bytes.fromhex(hash_hex)
        if len(h) != 32:
            raise ValueError("bad_len")
        return wc, h
    except Exception as e:
        logger.warning("TON _parse_ton_address error for addr=%s: %s", addr, e)
        raise HTTPException(400, "bad_ton_address") from e


# ---------- TON Auth ----------


def _b64decode(s: str) -> bytes:
    try:
        return base64.b64decode(s, validate=True)
    except Exception as e:
        raise HTTPException(400, "bad_base64") from e


def _b64decode_loose(s: str) -> bytes:
    """
    Accept base64 or base64url, with/without padding.
    """
    try:
        return base64.b64decode(s, validate=False)
    except Exception:
        pass
    try:
        padded = s + "=" * ((4 - len(s) % 4) % 4)
        return base64.urlsafe_b64decode(padded)
    except Exception as e:
        raise HTTPException(400, "bad_base64") from e


def _decode_signature(sig: str) -> bytes:
    """
    TonConnect signData.signature — base64, но на всякий случай принимаем и hex.
    """
    try:
        return _b64decode_loose(sig)
    except Exception:
        pass
    try:
        clean = sig[2:] if sig.startswith("0x") else sig
        return bytes.fromhex(clean)
    except Exception as e:
        raise HTTPException(400, "bad_signature_format") from e


def _derive_ton_address(pubkey: bytes) -> str:
    return pubkey.hex()


def _derive_eth_from_ton_pub(pubkey: bytes) -> str:
    digest = keccak(pubkey)
    return "0x" + digest[-20:].hex()


def _ton_payload_bytes(payload: dict) -> bytes:
    """
    Достаём именно байты, которые TonConnect подписывает.
    """
    ptype = payload.get("type")
    if ptype == "binary":
        val = payload.get("bytes")
        if not isinstance(val, str):
            raise HTTPException(400, "bad_payload")
        try:
            return _b64decode_loose(val)
        except HTTPException as err:
            raise HTTPException(400, "bad_payload_b64") from err
    if ptype == "text":
        val = payload.get("text")
        if not isinstance(val, str):
            raise HTTPException(400, "bad_payload")
        return val.encode("utf-8")
    raise HTTPException(400, "unsupported_payload_type")


def _parse_raw_ton_address(addr: str) -> tuple[int, bytes]:
    """
    raw-адрес формата "<workchain>:<hex32>" -> (wc, hash32)
    Пример: "0:0e92..."
    """
    try:
        wc_str, hash_hex = addr.split(":", 1)
        wc = int(wc_str)
        h = bytes.fromhex(hash_hex)
        if len(h) != 32:
            raise ValueError("bad_len")
        return wc, h
    except Exception as e:
        logger.warning("TON _parse_raw_ton_address error for %s: %s", addr, e)
        raise HTTPException(400, "bad_ton_address") from e


def _ton_sign_data_message_variants(
    address: str,
    domain: str,
    timestamp: int,
    payload_raw: bytes,
    ptype: str,
) -> list[bytes]:
    """
    Генерируем множество разумных вариантов сообщения для signData:

      message ~= [0xffff?] ++ prefix_str ++ Address ++ DomainPart ++ TimestampPart ++ PayloadPart

    Где:
      Address      = wc_be(int32) ++ hash32
      DomainPart   = либо le32(len)+dom, либо be32(len)+dom, либо просто dom, либо пусто
      TimestampPart= ts_le64 / ts_be64 / ts_le32 / ts_be32 / пусто
      PayloadPart  = один из:
                     - "txt"/"bin" + le32(len) + data
                     - "txt"/"bin" + be32(len) + data
                     - "txt"/"bin" + data
                     - просто data

    prefix_str варианты:
      "ton-connect/sign-data/",
      "ton-connect/sign-data",
      "ton-connect-sign-data/",
      "ton-connect-sign-data"

    И с/без префикса 0xffff.
    """
    wc, addr_hash = _parse_raw_ton_address(address)
    wc_bytes = int(wc).to_bytes(4, "big", signed=True)

    dom_bytes = (domain or "").encode("utf-8")
    dom_le = len(dom_bytes).to_bytes(4, "little", signed=False)
    dom_be = len(dom_bytes).to_bytes(4, "big", signed=False)

    ts_le64 = int(timestamp).to_bytes(8, "little", signed=False)
    ts_be64 = int(timestamp).to_bytes(8, "big", signed=False)
    ts_le32 = (int(timestamp) & 0xFFFFFFFF).to_bytes(4, "little", signed=False)
    ts_be32 = (int(timestamp) & 0xFFFFFFFF).to_bytes(4, "big", signed=False)

    if ptype == "text":
        prefix_tag = b"txt"
    else:
        prefix_tag = b"bin"

    payload_len_le = len(payload_raw).to_bytes(4, "little", signed=False)
    payload_len_be = len(payload_raw).to_bytes(4, "big", signed=False)

    prefix_leads = [b"", b"\xff\xff"]
    label_variants = [
        b"ton-connect/sign-data/",
        b"ton-connect/sign-data",
        b"ton-connect-sign-data/",
        b"ton-connect-sign-data",
    ]

    domain_parts = [
        b"",                          # без домена
        dom_bytes,                    # только домен
        dom_le + dom_bytes,           # длина LE + домен
        dom_be + dom_bytes,           # длина BE + домен
    ]

    ts_parts = [
        b"",       # без timestamp
        ts_le64,
        ts_be64,
        ts_le32,
        ts_be32,
    ]

    payload_parts = [
        prefix_tag + payload_len_le + payload_raw,
        prefix_tag + payload_len_be + payload_raw,
        prefix_tag + payload_raw,
        payload_raw,
    ]

    variants: list[bytes] = []
    for lead in prefix_leads:
        for label in label_variants:
            for d in domain_parts:
                for tsb in ts_parts:
                    for pb in payload_parts:
                        msg = b"".join(
                            [
                                lead,
                                label,
                                wc_bytes,
                                addr_hash,
                                d,
                                tsb,
                                pb,
                            ]
                        )
                        variants.append(msg)

    logger.warning(
        "TON _ton_sign_data_message_variants: generated %d variants for address=%s",
        len(variants),
        address,
    )
    return variants


def _verify_ton_sign_data(
    pubkey: bytes,
    signature: bytes,
    address: str,
    domain: str,
    timestamp: int,
    payload: dict,
) -> tuple[bool, bytes]:
    """
    Перебираем множество реалистичных вариантов формата signData и
    пытаемся проверить подпись:

      sig = Ed25519( sha256( message_variant ) )

    Если ни один вариант не подходит — возвращаем False.
    """
    ptype = payload.get("type")
    payload_raw = _ton_payload_bytes(payload)

    variants = _ton_sign_data_message_variants(
        address=address,
        domain=domain or "",
        timestamp=int(timestamp),
        payload_raw=payload_raw,
        ptype=ptype,
    )

    pub = Ed25519PublicKey.from_public_bytes(pubkey)

    # Сначала пробуем сигнатуру по sha256(message)
    for idx, msg in enumerate(variants, start=1):
        digest = hashlib.sha256(msg).digest()
        try:
            pub.verify(signature, digest)
            logger.warning(
                "TON _verify_ton_sign_data: signature OK on variant #%d (sha256(message))",
                idx,
            )
            return True, payload_raw
        except InvalidSignature:
            continue
        except Exception as e:
            logger.warning(
                "TON _verify_ton_sign_data: unexpected error on variant #%d: %s",
                idx,
                e,
            )
            continue

    # На всякий пожарный — пробуем, вдруг кошелёк подписывает сырое message
    for idx, msg in enumerate(variants, start=1):
        try:
            pub.verify(signature, msg)
            logger.warning(
                "TON _verify_ton_sign_data: signature OK on variant #%d (raw message)",
                idx,
            )
            return True, payload_raw
        except InvalidSignature:
            continue
        except Exception as e:
            logger.warning(
                "TON _verify_ton_sign_data: unexpected error (raw) on variant #%d: %s",
                idx,
                e,
            )
            continue

    logger.warning(
        "TON _verify_ton_sign_data: all %d variants failed verification", len(variants)
    )
    return False, payload_raw



@router.post("/ton/challenge", response_model=ChallengeOut)
def ton_challenge(body: dict) -> ChallengeOut:
    pubkey_b64 = body.get("pubkey")
    if not isinstance(pubkey_b64, str):
        logger.warning("TON /ton/challenge: pubkey_required, body=%s", body)
        raise HTTPException(400, "pubkey_required")

    pubkey = _b64decode(pubkey_b64)
    if len(pubkey) != 32:
        logger.warning(
            "TON /ton/challenge: bad_pubkey length=%d body=%s", len(pubkey), body
        )
        raise HTTPException(400, "bad_pubkey")

    challenge_id = str(uuidlib.uuid4())
    # nonce как base64(32 байт), чтобы удобно класть в signData.payload.bytes
    nonce_bytes = secrets.token_bytes(32)
    nonce = base64.b64encode(nonce_bytes).decode()

    rds.setex(
        f"auth:ton:chal:{challenge_id}",
        TON_CHALLENGE_TTL,
        json.dumps({"nonce": nonce, "pubkey": pubkey_b64}),
    )

    logger.warning(
        "TON /ton/challenge OK: challenge_id=%s nonce=%s pubkey_prefix=%s",
        challenge_id,
        nonce,
        pubkey.hex()[:16] + "…" if pubkey else "<none>",
    )

    return ChallengeOut(challenge_id=challenge_id, nonce=nonce, exp_sec=TON_CHALLENGE_TTL)


@router.post("/ton/login", response_model=Tokens)
def ton_login(body: dict, db: Annotated[Session, Depends(get_db)]) -> Tokens:
    logger.warning("TON /ton/login raw body=%s", body)

    challenge_id = body.get("challenge_id")
    signature_b64 = body.get("signature")
    domain = body.get("domain", "")
    timestamp = body.get("timestamp")
    payload_obj = body.get("payload")
    address = body.get("address")

    if not isinstance(challenge_id, str) or not isinstance(signature_b64, str):
        logger.warning("TON /ton/login: bad_request id/sig, body=%s", body)
        raise HTTPException(400, "bad_request")

    if not isinstance(timestamp, (int, float)):
        logger.warning("TON /ton/login: bad_timestamp type=%s body=%s", type(timestamp), body)
        raise HTTPException(400, "bad_request")

    if not isinstance(payload_obj, dict):
        logger.warning("TON /ton/login: payload_required, body=%s", body)
        raise HTTPException(400, "payload_required")

    if not isinstance(address, str):
        logger.warning("TON /ton/login: address_required, body=%s", body)
        raise HTTPException(400, "address_required")

    key = f"auth:ton:chal:{challenge_id}"
    raw = rds.get(key)
    if not raw:
        logger.warning("TON /ton/login: challenge_expired id=%s", challenge_id)
        raise HTTPException(410, "challenge_expired")

    try:
        data = json.loads(raw if isinstance(raw, str) else raw.decode())
        nonce_b64 = data["nonce"]
        pubkey_b64 = data["pubkey"]
    except Exception as e:
        logger.warning("TON /ton/login: challenge_invalid id=%s raw=%s err=%s", challenge_id, raw, e)
        raise HTTPException(400, "challenge_invalid") from e

    nonce = _b64decode_loose(nonce_b64)
    pubkey = _b64decode_loose(pubkey_b64)
    signature = _decode_signature(signature_b64)

    logger.warning(
        "TON /ton/login: loaded challenge=%s nonce_len=%d pubkey_prefix=%s sig_len=%d",
        challenge_id,
        len(nonce),
        pubkey.hex()[:16] + "…" if pubkey else "<none>",
        len(signature),
    )

    # Проверка подписи по TonConnect SignData spec
    ok, payload_raw = _verify_ton_sign_data(
        pubkey,
        signature,
        address,
        str(domain or ""),
        int(timestamp),
        payload_obj,
    )

    logger.warning(
        "TON /ton/login: verify result ok=%s payload_len=%d", ok, len(payload_raw)
    )

    # Жёстко сверяем, что payload соответствует выданному challenge.nonce
    # (для binary-пейлоада)
    if payload_obj.get("type") == "binary":
        try:
            nonce_from_payload = _ton_payload_bytes(payload_obj)
        except HTTPException:
            logger.warning(
                "TON /ton/login: bad_payload while decoding payload_obj=%s", payload_obj
            )
            raise
        if nonce_from_payload != nonce:
            logger.warning(
                "TON /ton/login: payload != nonce (challenge=%s, payload_len=%d, nonce_len=%d)",
                challenge_id,
                len(nonce_from_payload),
                len(nonce),
            )
            raise HTTPException(401, "payload_mismatch")

    if not ok:
        logger.warning(
            "TON /ton/login: invalid signature (challenge=%s pubkey=%s sig_len=%d nonce_len=%d)",
            challenge_id,
            pubkey.hex()[:16] + "…" if pubkey else "<none>",
            len(signature),
            len(nonce),
        )
        raise HTTPException(401, "bad_signature")

    # consume challenge
    try:
        rds.delete(key)
    except Exception:
        logger.warning(
            "TON /ton/login: failed to delete challenge key %s", key, exc_info=True
        )

    # find or create user bound to this TON pubkey
    user = db.query(User).filter(User.ton_pubkey == pubkey).one_or_none()
    if user is None:
        user = db.query(User).filter(
            User.eth_address == _derive_eth_from_ton_pub(pubkey)
        ).one_or_none()

    if user is None:
        user = User(
            eth_address=_derive_eth_from_ton_pub(pubkey),
            rsa_public=pubkey_b64,
            ton_pubkey=pubkey,
            display_name="TON user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.warning(
            "TON /ton/login: created new user id=%s eth=%s",
            user.id,
            user.eth_address,
        )
    else:
        if user.ton_pubkey is None:
            user.ton_pubkey = pubkey
            db.add(user)
            db.commit()
            logger.warning(
                "TON /ton/login: attached ton_pubkey to user id=%s", user.id
            )

    # embed ton pubkey for downstream checks
    access_payload = {"sub": str(user.id), "ton_pubkey": _derive_ton_address(pubkey)}
    access = make_token(access_payload, 30)
    refresh = make_token(str(user.id), 24 * 60)
    logger.warning("TON /ton/login: success user_id=%s", user.id)
    return Tokens(access=access, refresh=refresh)



# ---------- ETH register/login ----------


@router.post(
    "/register",
    response_model=Tokens,
    dependencies=[
        Depends(
            rate_limit(
                "auth_register",
                3,
                3600,
                require_json_keys=(
                    "eth_address",
                    "challenge_id",
                    "signature",
                    "typed_data",
                    "rsa_public",
                ),
            )
        )
    ],
)
def register(payload: RegisterIn, db: Annotated[Session, Depends(get_db)]) -> Tokens:
    key = f"auth:chal:{payload.challenge_id}"
    raw = rds.get(key)
    if not raw:
        raise HTTPException(400, "challenge_expired")

    if isinstance(raw, (bytes, bytearray)):
        raw_str = raw.decode("utf-8")
    elif isinstance(raw, str):
        raw_str = raw
    else:
        raw_str = cast(str, raw)
    data = json.loads(raw_str)

    td: dict[str, Any] = (
        payload.typed_data.model_dump()
        if hasattr(payload.typed_data, "model_dump")
        else cast(dict[str, Any], payload.typed_data)
    )
    validate_login_typed_data(td, data["nonce"], payload.eth_address)

    signer = _verify_login_signature(td, payload.signature)
    logger.info("login verify: signer=%s provided=%s", signer, payload.eth_address)
    if signer.lower() != payload.eth_address.lower():
        raise HTTPException(401, "bad_signature")

    user = db.query(User).filter(User.eth_address == payload.eth_address.lower()).one_or_none()
    if not user:
        user = User(
            eth_address=payload.eth_address.lower(),
            rsa_public=payload.rsa_public,
            display_name=payload.display_name,
        )
        db.add(user)
        db.commit()

    try:
        rds.delete(key)
    except Exception:
        logger.warning("register: failed to delete challenge key %s from redis", key, exc_info=True)

    access = make_token(str(user.id), 30)
    refresh = make_token(str(user.id), 24 * 60)
    return Tokens(access=access, refresh=refresh)


@router.post(
    "/login",
    response_model=Tokens,
    dependencies=[
        Depends(
            rate_limit(
                "auth_login",
                10,
                3600,
                require_json_keys=("eth_address", "challenge_id", "signature", "typed_data"),
            )
        )
    ],
)
def login(payload: LoginIn, db: Annotated[Session, Depends(get_db)]) -> Tokens:
    key = f"auth:chal:{payload.challenge_id}"
    raw = rds.get(key)
    if not raw:
        raise HTTPException(400, "challenge_expired")

    if isinstance(raw, (bytes, bytearray)):
        raw_str = raw.decode("utf-8")
    elif isinstance(raw, str):
        raw_str = raw
    else:
        raw_str = cast(str, raw)
    data = json.loads(raw_str)

    td: dict[str, Any] = (
        payload.typed_data.model_dump()
        if hasattr(payload.typed_data, "model_dump")
        else cast(dict[str, Any], payload.typed_data)
    )
    validate_login_typed_data(td, data["nonce"], payload.eth_address)

    signer = _verify_login_signature(td, payload.signature)
    logger.info("login verify: signer=%s provided=%s", signer, payload.eth_address)
    if signer.lower() != payload.eth_address.lower():
        raise HTTPException(401, "bad_signature")

    user = db.query(User).filter(User.eth_address == payload.eth_address.lower()).one_or_none()
    if not user:
        raise HTTPException(401, "user_not_found")

    try:
        rds.delete(key)
    except Exception:
        logger.warning("login: failed to delete challenge key %s from redis", key, exc_info=True)

    access = make_token(str(user.id), 30)
    refresh = make_token(str(user.id), 24 * 60)
    return Tokens(access=access, refresh=refresh)
