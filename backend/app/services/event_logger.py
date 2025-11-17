"""Event logging service for audit trail and anchoring."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from eth_hash.auto import keccak
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import SessionLocal  # use isolated session
from app.models.events import Event

log = logging.getLogger(__name__)


class EventLogger:
    """Service for logging events to database for anchoring."""

    def __init__(self, db: Session | None = None) -> None:
        # keep signature compatible; db is unused now (we use isolated sessions)
        self._unused_db = db

    @staticmethod
    def compute_period_id(ts: datetime | None = None) -> int:
        """
        Compute period_id from timestamp.
        period_id = floor(timestamp / period_seconds)
        """
        if ts is None:
            ts = datetime.now(UTC)
        # Convert to Unix timestamp
        timestamp = int(ts.timestamp())
        period_seconds = settings.anchor_period_min * 60
        return timestamp // period_seconds

    @staticmethod
    def compute_payload_hash(payload: dict[str, Any]) -> bytes:
        """
        Compute keccak256 hash of JSON payload for privacy.
        Returns 32 bytes.
        """
        # Sort keys for deterministic hashing
        json_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return keccak(json_str.encode("utf-8"))

    def _persist_event_isolated(self, event: Event) -> Event:
        """Persist event using a separate SessionLocal, swallow errors."""
        try:
            with SessionLocal() as s:  # type: ignore[call-arg]
                s.add(event)
                s.commit()
                try:
                    s.refresh(event)
                except Exception as e:
                    log.debug("EventLogger: s.refresh failed: %s", e, exc_info=True)
        except Exception as e:
            log.warning("EventLogger: failed to persist event: %s", e)
        return event

    def log_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        file_id: bytes | None = None,
        user_id: UUID | None = None,
        ts: datetime | None = None,
    ) -> Event:
        """
        Log an event to the database.

        Args:
            event_type: Type of event (file_registered, grant_created, etc.)
            payload: Dictionary with event details
            file_id: Optional file_id (32 bytes)
            user_id: Optional user_id (UUID)
            ts: Optional timestamp (defaults to now)

        Returns:
            Created Event instance
        """
        if ts is None:
            ts = datetime.now(UTC)
        period_id = self.compute_period_id(ts)
        payload_hash = self.compute_payload_hash(payload)

        # omit file_id to avoid schema/type mismatch issues across migrations
        safe_file_id: bytes | None = None

        event = Event(
            period_id=period_id,
            ts=ts,
            type=event_type,
            file_id=safe_file_id,
            user_id=user_id,
            payload_hash=payload_hash,
        )

        return self._persist_event_isolated(event)

    def log_file_registered(
        self, file_id: bytes, owner_id: UUID, cid: str, checksum: bytes, size: int
    ) -> Event:
        """Log file registration event."""
        payload = {
            "file_id": file_id.hex(),
            "owner_id": str(owner_id),
            "cid": cid,
            "checksum": checksum.hex(),
            "size": size,
        }
        return self.log_event(
            event_type="file_registered",
            payload=payload,
            file_id=None,
            user_id=owner_id,
        )

    def log_grant_created(
        self,
        cap_id: bytes,
        file_id: bytes,
        grantor_id: UUID,
        grantee_id: UUID,
        ttl_seconds: int,
        max_downloads: int,
    ) -> Event:
        """Log grant creation event."""
        payload = {
            "cap_id": cap_id.hex(),
            "file_id": file_id.hex(),
            "grantor_id": str(grantor_id),
            "grantee_id": str(grantee_id),
            "ttl_seconds": ttl_seconds,
            "max_downloads": max_downloads,
        }
        return self.log_event(
            event_type="grant_created",
            payload=payload,
            file_id=None,
            user_id=grantor_id,
        )

    def log_grant_revoked(self, cap_id: bytes, file_id: bytes, revoker_id: UUID) -> Event:
        """Log grant revocation event."""
        payload = {
            "cap_id": cap_id.hex(),
            "file_id": file_id.hex(),
            "revoker_id": str(revoker_id),
        }
        return self.log_event(
            event_type="grant_revoked",
            payload=payload,
            file_id=None,
            user_id=revoker_id,
        )

    def log_grant_used(
        self, cap_id: bytes, file_id: bytes, user_id: UUID, download_size: int
    ) -> Event:
        """Log grant usage (download) event."""
        payload = {
            "cap_id": cap_id.hex(),
            "file_id": file_id.hex(),
            "user_id": str(user_id),
            "download_size": download_size,
        }
        return self.log_event(
            event_type="grant_used",
            payload=payload,
            file_id=None,
            user_id=user_id,
        )
