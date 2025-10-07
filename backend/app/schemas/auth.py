from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Dict
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
import json



class ChallengeOut(BaseModel):
    challenge_id: str
    nonce: str  # hex 32 bytes
    exp_sec: int

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


class TypedData(BaseModel):
    domain: Dict[str, Any]
    types: Dict[str, Any]
    primaryType: str
    message: Dict[str, Any]

class RegisterIn(BaseModel):
    challenge_id: str
    eth_address: str
    rsa_public: str
    display_name: str | None = None
    typed_data: TypedData | str
    signature: str

    @field_validator("typed_data", mode="before")
    @classmethod
    def parse_typed_data(cls, v):
        # Принимаем как raw JSON-объект или как строку (Postman/axios особенности)
        if isinstance(v, (dict, TypedData)):
            return v
        if isinstance(v, str):
            try:
                return TypedData.model_validate(json.loads(v))
            except Exception as e:
                raise ValueError(f"typed_data_invalid: {e}")
        raise ValueError("typed_data must be object or JSON string")



class LoginIn(BaseModel):
    challenge_id: str
    eth_address: str
    typed_data: TypedData | str
    signature: str

    @field_validator("typed_data", mode="before")
    @classmethod
    def parse_typed_data(cls, v):
        if isinstance(v, (dict, TypedData)):
            return v
        if isinstance(v, str):
            return TypedData.model_validate(json.loads(v))
        raise ValueError("typed_data must be object or JSON string")