# backend/app/schemas/bot.py
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class BotFile(BaseModel):
    """Compact file representation for bot responses."""

    id_hex: str = Field(..., description="File ID as a hex string (32 bytes)")
    name: str
    size: int
    mime: str | None
    cid: str
    created_at: datetime = Field(..., alias="updatedAt")

    class Config:
        populate_by_name = True


class BotFileListResponse(BaseModel):
    """Response with a list of files and a cursor for the next page."""

    files: list[BotFile]
    cursor: str | None = Field(
        None,
        description="Cursor for the next page (ISO timestamp)",
    )


class GrantDirection(str, Enum):
    """Direction of grants for filtering."""

    IN = "in"
    OUT = "out"


class BotGrant(BaseModel):
    """Compact grant representation for bot responses."""

    capId: str = Field(..., description="Grant Capability ID in hex format")
    fileName: str
    used: int
    max_dl: int = Field(..., alias="max")  # use max_dl from the model and return as max
    expiresAt: datetime
    status: str  # "active", "expired", "revoked", "used_up"

    class Config:
        populate_by_name = True


class BotGrantListResponse(BaseModel):
    """Response with a list of grants and a cursor for the next page."""

    grants: list[BotGrant]
    cursor: str | None = Field(
        None,
        description="Cursor for the next page (ISO timestamp)",
    )


class BotProfileResponse(BaseModel):
    """User profile for the bot (/bot/me)."""

    address: str = Field(..., description="User's linked wallet address")
    display_name: str | None = Field(
        None,
        description="User's display name, if set",
    )
