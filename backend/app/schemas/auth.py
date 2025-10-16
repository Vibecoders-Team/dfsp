from __future__ import annotations

from pydantic import BaseModel


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


import json
from typing import Dict, Any

from pydantic import BaseModel, field_validator


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
    # Храним в модели уже TypedData (сериализация/валидация сделает экземпляр)
    typed_data: TypedData
    signature: str

    @field_validator("typed_data", mode="before")
    def parse_typed_data(cls, v):
        # Принимаем как raw JSON-объект или как строку (Postman/axios особенности)
        if isinstance(v, TypedData):
            return v
        if isinstance(v, dict):
            # возвращаем dict — Pydantic дальше превратит его в TypedData
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"typed_data_invalid: {e}") from e
            # проверим и вернём dict для дальнейшей валидации
            if isinstance(parsed, dict):
                return parsed
            raise ValueError("typed_data JSON must be an object")
        raise ValueError("typed_data must be object or JSON string")


class LoginIn(BaseModel):
    challenge_id: str
    eth_address: str
    typed_data: TypedData
    signature: str

    @field_validator("typed_data", mode="before")
    def parse_typed_data(cls, v):
        # Подобная логика как в RegisterIn
        if isinstance(v, TypedData):
            return v
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"typed_data_invalid: {e}") from e
            if isinstance(parsed, dict):
                return parsed
            raise ValueError("typed_data JSON must be an object")
        raise ValueError("typed_data must be object or JSON string")
