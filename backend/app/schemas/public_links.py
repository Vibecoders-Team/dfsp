from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class OkOut(BaseModel):
    ok: bool = True


class PowIn(BaseModel):
    nonce: str
    solution: str


class PublicLinkCreateIn(BaseModel):
    version: int | None = None
    ttl_sec: int | None = None
    max_downloads: int | None = None
    pow: dict | None = None
    name_override: str | None = None
    mime_override: str | None = None


class PublicLinkCreateOut(BaseModel):
    token: str
    expires_at: datetime | None = None
    policy: PublicLinkPolicyOut


class PublicLinkPolicyOut(BaseModel):
    max_downloads: int | None = None
    pow_difficulty: int | None = None
    one_time: bool = False


class PublicMetaOut(BaseModel):
    name: str
    size: int | None = None
    mime: str | None = None
    cid: str | None = None
    fileId: str
    version: int | None = None
    expires_at: datetime | None = None
    policy: PublicLinkPolicyOut


class RevokeOut(BaseModel):
    revoked: bool = True


class PublicLinkItemOut(BaseModel):
    token: str
    expires_at: datetime | None = None
    policy: PublicLinkPolicyOut
    downloads_count: int = 0


class PublicLinksListOut(BaseModel):
    items: list[PublicLinkItemOut]
