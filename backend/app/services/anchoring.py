"""Anchoring service for Merkle tree construction and on-chain anchoring."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from eth_hash.auto import keccak
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.anchors import Anchor
from app.models.events import Event

log = logging.getLogger(__name__)


class MerkleTree:
    """Simple Merkle tree implementation for event anchoring."""

    def __init__(self, leaves: list[bytes]) -> None:
        """
        Initialize Merkle tree from leaf hashes.

        Args:
            leaves: List of 32-byte hashes (leaf nodes)
        """
        if not leaves:
            # Empty tree has zero root
            self.root = b"\x00" * 32
            self.leaves = []
            return

        self.leaves = leaves
        self.root = self._build_tree(leaves)

    def _build_tree(self, nodes: list[bytes]) -> bytes:
        """Recursively build Merkle tree and return root."""
        if len(nodes) == 1:
            return nodes[0]

        # Pair up nodes and hash them
        next_level: list[bytes] = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            # If odd number of nodes, duplicate the last one
            right = nodes[i + 1] if i + 1 < len(nodes) else left
            # Hash concatenation: keccak256(left || right)
            parent = keccak(left + right)
            next_level.append(parent)

        return self._build_tree(next_level)

    @classmethod
    def from_events(cls, events: list[Event]) -> MerkleTree:
        """
        Build Merkle tree from events.

        Leaf = keccak256(event.id || event.type || event.payload_hash || event.ts)
        """
        leaves: list[bytes] = []
        for event in events:
            # Concatenate fields for leaf hash
            # id as 8-byte big-endian integer
            id_bytes = event.id.to_bytes(8, byteorder="big")
            type_bytes = event.type.encode("utf-8")
            # timestamp as Unix timestamp (8 bytes)
            ts_unix = int(event.ts.timestamp())
            ts_bytes = ts_unix.to_bytes(8, byteorder="big")

            # Concatenate: id || type || payload_hash || ts
            leaf_data = id_bytes + type_bytes + event.payload_hash + ts_bytes
            leaf_hash = keccak(leaf_data)
            leaves.append(leaf_hash)

        return cls(leaves)


class AnchoringService:
    """Service for anchoring events to blockchain via Merkle root."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_events_for_period(self, period_id: int) -> list[Event]:
        """Fetch all events for a given period."""
        stmt = select(Event).where(Event.period_id == period_id).order_by(Event.id)
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def compute_merkle_root(self, events: list[Event]) -> bytes:
        """Compute Merkle root from events."""
        tree = MerkleTree.from_events(events)
        return tree.root

    def anchor_period(self, period_id: int, tx_hash: str | None = None) -> Anchor:
        """
        Anchor a period by computing Merkle root and storing in database.

        Args:
            period_id: Period ID to anchor
            tx_hash: Optional transaction hash (if already submitted on-chain)

        Returns:
            Created Anchor instance
        """
        # Check if already anchored
        existing = self.db.execute(select(Anchor).where(Anchor.period_id == period_id)).scalar_one_or_none()

        if existing:
            log.warning(f"Period {period_id} already anchored: {existing.id}")
            return existing

        # Get events for this period
        events = self.get_events_for_period(period_id)

        if not events:
            log.warning(f"No events found for period {period_id}, skipping anchor")
            # Create anchor with zero root to mark period as processed
            root = b"\x00" * 32
        else:
            root = self.compute_merkle_root(events)
            log.info(f"Computed Merkle root for period {period_id}: {root.hex()} ({len(events)} events)")

        # Create anchor record
        anchor = Anchor(
            period_id=period_id,
            root=root,
            created_at=datetime.now(UTC),
        )

        self.db.add(anchor)
        self.db.commit()
        self.db.refresh(anchor)

        log.info(f"Anchored period {period_id}: anchor_id={anchor.id}")

        return anchor

    def get_latest_anchor(self) -> Anchor | None:
        """Get the most recent anchor."""
        stmt = select(Anchor).order_by(Anchor.created_at.desc()).limit(1)
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def get_anchor_by_period(self, period_id: int) -> Anchor | None:
        """Get anchor for specific period."""
        stmt = select(Anchor).where(Anchor.period_id == period_id)
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()
