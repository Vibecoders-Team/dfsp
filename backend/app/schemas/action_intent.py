from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ActionIntentCreateIn(BaseModel):
    type: str = Field(..., min_length=1, max_length=128, description="Action type identifier")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary JSON-serializable parameters for this intent",
    )


class ActionIntentCreateOut(BaseModel):
    state: str
    expires_at: datetime


class ActionIntentConsumeIn(BaseModel):
    state: str = Field(..., description="Opaque state token obtained from /bot/action-intents")


class ActionIntentConsumeOut(BaseModel):
    type: str
    params: dict[str, Any]
