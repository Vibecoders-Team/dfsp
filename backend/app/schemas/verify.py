from __future__ import annotations

from pydantic import BaseModel, Field


class FileMeta(BaseModel):
    """Schema for representing file metadata (on-chain or off-chain)."""

    cid: str
    checksum: str = Field(pattern=r"^0x[0-9a-fA-F]{64}$")
    size: int
    mime: str | None
    name: str | None = None


class VerifyOut(BaseModel):
    """Response schema for the verification endpoint."""

    onchain: FileMeta | None = None
    offchain: FileMeta | None = None
    match: bool
