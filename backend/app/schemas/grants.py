from __future__ import annotations

import re
from typing import Dict, List

from pydantic import BaseModel, Field, field_validator

ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
HEX32_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")


class ShareIn(BaseModel):
    users: List[str] = Field(default_factory=list, description="Ethereum addresses 0x..")
    ttl_days: int = Field(..., ge=1, le=365)
    max_dl: int = Field(..., ge=1, le=1000)
    encK_map: Dict[str, str] = Field(default_factory=dict)
    request_id: str

    @field_validator("users")
    @classmethod
    def validate_users(cls, v: List[str]):
        if not v:
            raise ValueError("users_required")
        uniq: list[str] = []
        seen: set[str] = set()
        for a in v:
            if not isinstance(a, str) or not ADDR_RE.match(a):
                raise ValueError("bad_address")
            al = a.lower()
            if al not in seen:
                seen.add(al)
                uniq.append(a)
        return uniq


class ShareItemOut(BaseModel):
    grantee: str
    capId: str
    status: str


class ShareOut(BaseModel):
    items: List[ShareItemOut]
    # Полный список typedData — для всех получателей
    typedDataList: List[dict] | None = None
    # Удобный шорткат для случая, когда получатель один
    typedData: dict | None = None


class DuplicateOut(BaseModel):
    status: str
    capIds: List[str]
