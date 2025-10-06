from pydantic import BaseModel, Field
from typing import Optional, Dict
from typing import Optional, Dict, Any


class ChallengeOut(BaseModel):
    challenge_id: str
    nonce: str  # hex 32 bytes
    exp_sec: int

class RegisterIn(BaseModel):
    rsa_public: str
    eth_address: str
    display_name: Optional[str] = None
    challenge_id: str
    signature: str
    typed_data: Optional[Dict[str, Any]] = None  # ← стало optional

class LoginIn(BaseModel):
    eth_address: str
    challenge_id: str
    signature: str
    typed_data: Optional[Dict[str, Any]] = None  # ← стало optional

class Tokens(BaseModel):
    access: str
    refresh: str

class FileCreateIn(BaseModel):
    fileId: str  # 0x...32
    name: str
    size: int
    mime: str
    cid: str
    checksum: str  # 0x...32

class TypedDataOut(BaseModel):
    typedData: dict

class MetaTxSubmitIn(BaseModel):
    request_id: str
    typed_data: dict
    signature: str

class FileRow(BaseModel):
    id: str
    name: str
    size: int
    mime: str
    cid: str
    checksum: str
    status: str

class VerifyOut(BaseModel):
    onchain: dict
    offchain: dict
    match: bool
