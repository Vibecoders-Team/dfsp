from __future__ import annotations

import json
import logging
import re
import secrets
from os import getenv
from typing import Any, cast

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

# --- Валидаторы ---
ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
NONCE_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
SIG_RE = re.compile(r"^0x[0-9a-fA-F]{130}$")


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise HTTPException(400, msg)


def _validate_inputs(eth_address: str, nonce_hex: str, signature: str) -> None:
    _require(
        isinstance(eth_address, str) and ADDR_RE.fullmatch(eth_address or "") is not None,
        "bad_eth_address",
    )
    _require(
        isinstance(nonce_hex, str) and NONCE_RE.fullmatch(nonce_hex or "") is not None, "bad_nonce"
    )
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
        raise HTTPException(400, f"typed_data_invalid: {e}")
    try:
        return Account.recover_message(msg, signature=signature)
    except Exception as e:
        raise HTTPException(401, f"bad_signature: {e}")


def _recover_login_with_nonce(eth_address: str, nonce_hex: str, signature: str) -> str:
    # Явная валидация ещё до вычисления дайджеста
    _validate_inputs(eth_address, nonce_hex, signature)

    digest = _eip712_digest_login(eth_address, nonce_hex)

    try:
        sig_bytes = bytes.fromhex(signature[2:])  # 65 байт
        sig = Signature(sig_bytes)
        pub = sig.recover_public_key_from_msg_hash(digest)
        return pub.to_checksum_address()
    except Exception:
        raise HTTPException(401, "bad_signature")


def build_login_typed_data(nonce_hex: str, eth_address: str) -> dict[str, Any]:
    # каноническая форма, которой сервер будет подписывать/проверять
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
    """Гибкая проверка структуры typed_data: допускает domain.chainId (опционально)."""
    _require(isinstance(td, dict), "typed_data_invalid")
    domain = td.get("domain")
    types = td.get("types")
    primary = td.get("primaryType")
    message = td.get("message")
    _require(primary == "LoginChallenge", "bad_primary_type")
    _require(isinstance(domain, dict), "bad_domain")
    _require(domain.get("name") == LOGIN_DOMAIN["name"], "bad_domain_name")
    _require(domain.get("version") == LOGIN_DOMAIN["version"], "bad_domain_version")
    # Если chainId присутствует — проверим на совпадение с ожидаемым (если задан)
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
    # setex(key, seconds, value)
    rds.setex(f"auth:chal:{challenge_id}", exp_sec, json.dumps({"nonce": nonce}))
    return ChallengeOut(challenge_id=challenge_id, nonce=nonce, exp_sec=exp_sec)


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
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> Tokens:
    key = f"auth:chal:{payload.challenge_id}"
    raw = rds.get(key)
    if not raw:
        raise HTTPException(400, "challenge_expired")

    # нормализуем тип для json.loads
    if isinstance(raw, (bytes, bytearray)):
        raw_str = raw.decode("utf-8")
    elif isinstance(raw, str):
        raw_str = raw
    else:
        raw_str = cast(str, raw)
    data = json.loads(raw_str)

    # нормализуем typed_data к dict[str, Any]
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

    # consume once
    try:
        rds.delete(key)
    except Exception:
        logger.debug("register: failed to delete challenge key %s from redis", key, exc_info=True)

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
def login(payload: LoginIn, db: Session = Depends(get_db)) -> Tokens:
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
        logger.debug("login: failed to delete challenge key %s from redis", key, exc_info=True)

    access = make_token(str(user.id), 30)
    refresh = make_token(str(user.id), 24 * 60)
    return Tokens(access=access, refresh=refresh)
