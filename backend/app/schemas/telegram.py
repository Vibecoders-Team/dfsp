from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# Schema for the request body to /tg/link-start
class TgLinkStartRequest(BaseModel):
    chat_id: int = Field(..., gt=0, description="Telegram User Chat ID")


# Schema for the response from /tg/link-start
class TgLinkStartResponse(BaseModel):
    link_token: str
    expires_at: datetime


# Schema for the request body to /tg/link-complete
class TgLinkCompleteRequest(BaseModel):
    link_token: str


# Standard successful response
class OkResponse(BaseModel):
    ok: bool = True
