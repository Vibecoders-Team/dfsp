import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json, secrets

from eth_account import Account
from eth_keys import keys
from eth_utils import keccak, to_canonical_address

from app.deps import get_db, rds
from ..models import User
from ..schemas.auth import ChallengeOut, RegisterIn, LoginIn, Tokens
from app.security import make_token

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_DOMAIN = {"name": "DFSP-Login", "version": "1"}

# --- Валидаторы ---
ADDR_RE  = re.compile(r"^0x[0-9a-fA-F]{40}$")
NONCE_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
SIG_RE   = re.compile(r"^0x[0-9a-fA-F]{130}$")

def _require(cond: bool, msg: str):
    if not cond:
        raise HTTPException(400, msg)

def _validate_inputs(eth_address: str, nonce_hex: str, signature: str):
    _require(isinstance(eth_address, str) and ADDR_RE.fullmatch(eth_address or ""), "bad_eth_address")
    _require(isinstance(nonce_hex, str)  and NONCE_RE.fullmatch(nonce_hex or ""),   "bad_nonce")
    _require(isinstance(signature, str)  and SIG_RE.fullmatch(signature or ""),     "bad_signature_format")

def _left_pad32(b: bytes) -> bytes:
    return (b"\x00" * (32 - len(b))) + b if len(b) < 32 else b[-32:]

def _eip712_digest_login(eth_address: str, nonce_hex: str) -> bytes:
    # домен: EIP712Domain(string name,string version)
    typehash_domain = keccak(text="EIP712Domain(string name,string version)")
    name_hash       = keccak(text=LOGIN_DOMAIN["name"])
    version_hash    = keccak(text=LOGIN_DOMAIN["version"])
    domain_sep      = keccak(typehash_domain + name_hash + version_hash)

    # тип: LoginChallenge(address address,bytes32 nonce)
    typehash_login  = keccak(text="LoginChallenge(address address,bytes32 nonce)")
    addr_word       = _left_pad32(to_canonical_address(eth_address))
    nonce32         = bytes.fromhex(nonce_hex[2:])           # уже проверен форматом
    struct_hash     = keccak(typehash_login + addr_word + nonce32)

    return keccak(b"\x19\x01" + domain_sep + struct_hash)

def _recover_login_with_nonce(eth_address: str, nonce_hex: str, signature: str) -> str:
    # Явная валидация ещё до вычисления дайджеста
    _validate_inputs(eth_address, nonce_hex, signature)

    digest = _eip712_digest_login(eth_address, nonce_hex)

    try:
        sig_bytes = bytes.fromhex(signature[2:])   # 65 байт
        sig = keys.Signature(sig_bytes)
        pub = sig.recover_public_key_from_msg_hash(digest)
        return pub.to_checksum_address()
    except Exception:
        raise HTTPException(401, "bad_signature")

def build_login_typed_data(nonce_hex: str, eth_address: str) -> dict:
    # каноническая форма, которой сервер будет подписывать/проверять
    return {
        "domain": LOGIN_DOMAIN,
        "types": {
            "LoginChallenge": [
                {"name": "address", "type": "address"},
                {"name": "nonce",   "type": "bytes32"},
            ]
        },
        "primaryType": "LoginChallenge",
        "message": {"address": eth_address, "nonce": nonce_hex},
    }

@router.post("/challenge", response_model=ChallengeOut)
def challenge():
    challenge_id = secrets.token_hex(16)
    nonce = "0x" + secrets.token_hex(32)
    exp_sec = 300
    rds.setex(f"auth:chal:{challenge_id}", exp_sec, json.dumps({"nonce": nonce}))
    return ChallengeOut(challenge_id=challenge_id, nonce=nonce, exp_sec=exp_sec)


@router.post("/register", response_model=Tokens)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    raw = rds.get(f"auth:chal:{payload.challenge_id}")
    if not raw:
        raise HTTPException(400, "challenge_expired")
    data = json.loads(raw)

    signer = _recover_login_with_nonce(payload.eth_address, data.get("nonce", ""), payload.signature)
    if signer.lower() != payload.eth_address.lower():
        raise HTTPException(401, "bad_signature")

    user = db.query(User).filter(User.eth_address == payload.eth_address.lower()).one_or_none()
    if not user:
        user = User(
            eth_address=payload.eth_address.lower(),
            rsa_public=payload.rsa_public,
            display_name=payload.display_name,
        )
        db.add(user); db.commit()

    access = make_token(str(user.id), 30)
    refresh = make_token(str(user.id), 24 * 60)
    return Tokens(access=access, refresh=refresh)


@router.post("/login", response_model=Tokens)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    raw = rds.get(f"auth:chal:{payload.challenge_id}")
    if not raw:
        raise HTTPException(400, "challenge_expired")
    data = json.loads(raw)

    signer = _recover_login_with_nonce(payload.eth_address, data.get("nonce", ""), payload.signature)
    if signer.lower() != payload.eth_address.lower():
        raise HTTPException(401, "bad_signature")

    user = db.query(User).filter(User.eth_address == payload.eth_address.lower()).one_or_none()
    if not user:
        raise HTTPException(401, "user_not_found")

    access = make_token(str(user.id), 30)
    refresh = make_token(str(user.id), 24 * 60)
    return Tokens(access=access, refresh=refresh)
