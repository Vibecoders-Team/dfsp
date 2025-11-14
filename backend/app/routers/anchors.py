"""API router for anchoring endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.deps import get_db, rds
from app.schemas.anchors import AnchorDetailResponse, AnchorResponse
from app.services.anchoring import AnchoringService
from app.tasks.anchor import anchor_period_task
from app.services.event_publisher import EventPublisher  # NEW

log = logging.getLogger(__name__)

router = APIRouter(prefix="/anchors", tags=["anchors"])


def _publish_anchor_ok(
    *,
    period_id: int,
    merkle_root: str,
    tx_hash: str | None,
    source: str,
) -> None:
    """
    anchor_ok: событие об успешном наличии/создании анкера.
    Считаем idempotent по (period_id, tx_hash).
    """
    try:
        publisher = EventPublisher()
        subject: dict[str, object] = {
            "periodId": period_id,
            "merkleRoot": merkle_root,
        }
        if tx_hash:
            subject["txHash"] = tx_hash

        payload = {"source": source}
        event_id = f"anchor_ok:{period_id}:{tx_hash or 'no_tx'}"
        publisher.publish("anchor_ok", subject=subject, payload=payload, event_id=event_id)
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to publish anchor_ok: %s", e)


@router.get("/latest", response_model=AnchorResponse)
def get_latest_anchor(
    db: Annotated[Session, Depends(get_db)],
) -> AnchorResponse:
    """
    Get the latest anchor.

    Returns:
        Latest anchor with period_id, merkle_root, and timestamp
    """
    service = AnchoringService(db)
    anchor = service.get_latest_anchor()

    if not anchor:
        raise HTTPException(status_code=404, detail="No anchors found")

    merkle_hex = anchor.root.hex()
    resp = AnchorResponse(
        period_id=anchor.period_id,
        merkle_root=merkle_hex,
        anchored_at=anchor.created_at,
        tx_hash=anchor.tx_hash,
    )

    # anchor_ok – фиксация того, что якорь успешно существует
    _publish_anchor_ok(
        period_id=anchor.period_id,
        merkle_root=merkle_hex,
        tx_hash=anchor.tx_hash,
        source="get_latest",
    )

    return resp


@router.get("/{period_id}", response_model=AnchorDetailResponse)
def get_anchor_by_period(
    period_id: Annotated[int, Path(ge=0)],
    db: Annotated[Session, Depends(get_db)],
) -> AnchorDetailResponse:
    """
    Get anchor details for a specific period.

    Args:
        period_id: Period ID to query

    Returns:
        Anchor details including events count
    """
    service = AnchoringService(db)
    anchor = service.get_anchor_by_period(period_id)

    if not anchor:
        raise HTTPException(status_code=404, detail=f"Anchor for period {period_id} not found")

    # Get event count for this period
    events = service.get_events_for_period(period_id)
    event_count = len(events)
    merkle_hex = anchor.root.hex()

    resp = AnchorDetailResponse(
        period_id=anchor.period_id,
        merkle_root=merkle_hex,
        anchored_at=anchor.created_at,
        tx_hash=anchor.tx_hash,
        event_count=event_count,
    )

    _publish_anchor_ok(
        period_id=anchor.period_id,
        merkle_root=merkle_hex,
        tx_hash=anchor.tx_hash,
        source="get_by_period",
    )

    return resp


@router.post("/trigger/{period_id}")
def trigger_anchoring(
    period_id: Annotated[int, Path(ge=0)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """
    Manually trigger anchoring for a specific period.

    Idempotent semantics:
    - If anchor already exists in DB OR scheduling marker exists in Redis, return {status: "already_anchored"}.
    - Otherwise, mark as scheduled and enqueue the task, return {status: "queued"}.
    """
    service = AnchoringService(db)
    existing = service.get_anchor_by_period(period_id)
    if existing:
        return {
            "status": "already_anchored",
            "period_id": str(period_id),
            "anchor_id": str(existing.id),
        }

    # Use Redis marker to ensure idempotency if DB row is not yet written but task already queued
    key = f"anchor:scheduled:{period_id}"
    try:
        # set key for 15 minutes only if not exists
        was_set = rds.set(key, "1", ex=15 * 60, nx=True)  # type: ignore[call-arg]
    except Exception:
        was_set = True  # fail-open: proceed to enqueue

    if not was_set:
        # Already scheduled by a previous call
        return {
            "status": "already_anchored",
            "period_id": str(period_id),
        }

    # Queue anchoring task
    result = anchor_period_task.apply_async(args=[period_id], queue="anchor")

    return {
        "status": "queued",
        "task_id": result.id,
        "period_id": str(period_id),
    }
