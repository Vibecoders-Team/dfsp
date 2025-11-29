from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.intent import Intent

router = APIRouter(prefix="/intents", tags=["intents"])

INTENT_TTL_SECONDS = int(os.getenv("INTENT_TTL_SECONDS", "900"))  # 15 min default
PUBLIC_WEB_ORIGIN = os.getenv("PUBLIC_WEB_ORIGIN", "http://localhost:3000").rstrip("/")


class IntentCreateIn(BaseModel):
    action: str = Field(pattern="^(share|revoke|delete_file)$")
    payload: dict


class IntentCreateOut(BaseModel):
    intent_id: uuid.UUID
    url: str
    ttl: int


class IntentConsumeOut(BaseModel):
    ok: bool
    action: str | None = None
    payload: dict | None = None


DbDep = Annotated[Session, Depends(get_db)]


@router.post("", response_model=IntentCreateOut, status_code=201)
def create_intent(body: IntentCreateIn, db: DbDep) -> IntentCreateOut:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=INTENT_TTL_SECONDS)
    intent = Intent(
        action=body.action,
        payload=body.payload,
        expires_at=expires_at,
    )
    db.add(intent)
    db.commit()
    db.refresh(intent)
    url = f"{PUBLIC_WEB_ORIGIN}/intent/{intent.id}"
    return IntentCreateOut(intent_id=intent.id, url=url, ttl=INTENT_TTL_SECONDS)


@router.post("/{intent_id}/consume", response_model=IntentConsumeOut)
def consume_intent(intent_id: uuid.UUID, db: DbDep) -> IntentConsumeOut:
    now = datetime.now(UTC)

    stmt = (
        update(Intent)
        .where(
            Intent.id == intent_id,
            Intent.used_at.is_(None),
            Intent.expires_at > now,
        )
        .values(used_at=now)
        .returning(Intent)
    )
    result = db.execute(stmt).scalar_one_or_none()
    if result:
        db.commit()
        return IntentConsumeOut(ok=True, action=result.action, payload=result.payload)

    # Inspect reason
    existing: Intent | None = db.scalar(select(Intent).where(Intent.id == intent_id))
    if existing is None:
        raise HTTPException(status_code=404, detail="intent_not_found")
    if existing.used_at is not None:
        raise HTTPException(status_code=409, detail="already_used")
    if existing.expires_at <= now:
        raise HTTPException(status_code=410, detail="expired")

    raise HTTPException(status_code=400, detail="invalid_state")
