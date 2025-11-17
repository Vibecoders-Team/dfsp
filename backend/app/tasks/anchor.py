"""Celery tasks for anchoring events."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from celery import Task

from app.config import settings
from app.db.session import SessionLocal
from app.relayer import celery
from app.services.anchoring import AnchoringService
from app.services.event_logger import EventLogger

log = logging.getLogger(__name__)


class DatabaseTask(Task):
    """Base task with database session management."""

    _db = None

    def after_return(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if self._db is not None:
            self._db.close()


@celery.task(bind=True, base=DatabaseTask, name="anchor.anchor_period")
def anchor_period_task(self: DatabaseTask, period_id: int | None = None) -> dict[str, str | int]:
    """
    Anchor events for a specific period.

    This task:
    1. Fetches all events for the period
    2. Builds Merkle tree from events
    3. Computes Merkle root
    4. Stores anchor in database
    5. (Future) Submits meta-tx to DFSPAnchoring contract

    Args:
        period_id: Period to anchor. If None, anchors the previous period.

    Returns:
        Dictionary with result information
    """
    db = SessionLocal()
    self._db = db

    try:
        # Determine which period to anchor
        if period_id is None:
            # Anchor previous period (current period - 1)
            current_period = EventLogger.compute_period_id(datetime.now(UTC))
            period_id = current_period - 1

        log.info(f"Starting anchoring for period {period_id}")

        anchoring_service = AnchoringService(db)

        # Check if already anchored
        existing = anchoring_service.get_anchor_by_period(period_id)
        if existing:
            log.info(f"Period {period_id} already anchored: {existing.id}")
            return {
                "status": "already_anchored",
                "period_id": period_id,
                "anchor_id": existing.id,
                "root": existing.root.hex(),
            }

        # Get events and compute merkle root
        events = anchoring_service.get_events_for_period(period_id)
        event_count = len(events)

        # Create anchor
        anchor = anchoring_service.anchor_period(period_id)

        log.info(
            f"Successfully anchored period {period_id}: "
            f"anchor_id={anchor.id}, events={event_count}, root={anchor.root.hex()}"
        )

        # TODO: Submit meta-tx to DFSPAnchoring.anchorMerkleRoot(root, periodId)
        # For now, we just store in database
        # In future sprint, integrate with blockchain/contracts.py

        return {
            "status": "success",
            "period_id": period_id,
            "anchor_id": anchor.id,
            "root": anchor.root.hex(),
            "event_count": event_count,
        }

    except Exception as e:
        log.exception(f"Failed to anchor period {period_id}: {e}")
        return {
            "status": "error",
            "period_id": period_id or -1,
            "error": str(e),
        }
    finally:
        db.close()


# Configure Celery Beat schedule for periodic anchoring
celery.conf.beat_schedule = {
    "anchor-events-hourly": {
        "task": "anchor.anchor_period",
        "schedule": settings.anchor_period_min * 60.0,  # Convert minutes to seconds
        "args": (),  # Will auto-determine previous period
        "options": {"queue": "anchor"},
    },
}
