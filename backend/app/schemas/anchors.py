"""Pydantic schemas for anchoring API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AnchorResponse(BaseModel):
    """Response schema for anchor queries."""

    period_id: int = Field(..., description="Period ID that was anchored")
    merkle_root: str = Field(..., description="Merkle root hash (hex)")
    anchored_at: datetime = Field(..., description="Timestamp when anchor was created")
    tx_hash: str | None = Field(None, description="On-chain transaction hash (if available)")

    model_config = {"from_attributes": True}


class AnchorDetailResponse(AnchorResponse):
    """Detailed anchor response including event count."""

    event_count: int = Field(..., description="Number of events in this period")

