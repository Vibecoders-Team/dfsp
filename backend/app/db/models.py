# app/db/models.py
from __future__ import annotations
import sqlalchemy as sa
from sqlalchemy import Index, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.db.base import Base

# ---------------- users ----------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    eth_address: Mapped[str] = mapped_column(sa.Text, unique=True, nullable=False)
    rsa_public: Mapped[str] = mapped_column(sa.Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


# ---------------- files ----------------
class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        # уникальность per-owner
        UniqueConstraint("owner_id", "checksum", name="uq_files_owner_checksum"),
        Index("ix_files_owner_created_at", "owner_id", "created_at"),
    )

    id: Mapped[bytes] = mapped_column(sa.LargeBinary(32), primary_key=True)  # bytes32
    owner_id: Mapped[str] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    size: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    mime: Mapped[str] = mapped_column(sa.Text, nullable=False)
    cid: Mapped[str] = mapped_column(sa.Text, nullable=False)
    checksum: Mapped[bytes] = mapped_column(sa.LargeBinary(32), nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


# ---------------- file_versions ----------------
class FileVersion(Base):
    __tablename__ = "file_versions"
    __table_args__ = (Index("ix_file_versions_file_created_at", "file_id", "created_at"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    file_id: Mapped[bytes] = mapped_column(sa.LargeBinary(32), sa.ForeignKey("files.id"), nullable=False)
    cid: Mapped[str] = mapped_column(sa.Text, nullable=False)
    checksum: Mapped[bytes] = mapped_column(sa.LargeBinary(32), nullable=False)
    size: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    mime: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


# ---------------- grants ----------------
class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (
        Index("ix_grants_grantee_exp", "grantee_id", "expires_at"),
        Index("ix_grants_file", "file_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    cap_id: Mapped[bytes] = mapped_column(sa.LargeBinary(32), unique=True, nullable=False)
    file_id: Mapped[bytes] = mapped_column(sa.LargeBinary(32), sa.ForeignKey("files.id"), nullable=False)
    grantor_id: Mapped[str] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    grantee_id: Mapped[str] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    max_dl: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    used: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    revoked_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)


# ---------------- events ----------------
class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_file_ts", "file_id", "ts"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    file_id: Mapped[bytes | None] = mapped_column(sa.LargeBinary(32), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ts: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    payload_hash: Mapped[bytes] = mapped_column(sa.LargeBinary(32), nullable=False)
    period_id: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)


# ---------------- anchors ----------------
class Anchor(Base):
    __tablename__ = "anchors"

    period_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    merkle_root: Mapped[bytes] = mapped_column(sa.LargeBinary(32), nullable=False)
    tx_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    anchored_ts: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


# ---------------- meta_tx_requests ----------------
class MetaTxRequest(Base):
    __tablename__ = "meta_tx_requests"
    __table_args__ = (
        sa.UniqueConstraint("request_id", name="uq_meta_tx_request_id"),
        Index("ix_meta_tx_status_updated", "status", "updated_at"),
    )

    request_id: Mapped[str] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    from_address: Mapped[str] = mapped_column(sa.Text, nullable=False)
    to_address: Mapped[str] = mapped_column(sa.Text, nullable=False)
    forwarder_addr: Mapped[str] = mapped_column(sa.Text, nullable=False)
    op_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    priority: Mapped[str] = mapped_column(sa.Text, server_default="default", nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, server_default="queued", nullable=False)
    tx_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    valid_until: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    message_nonce: Mapped[int | None] = mapped_column(sa.Numeric, nullable=True)
    typed_data: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    signature: Mapped[str] = mapped_column(sa.Text, nullable=False)
    last_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    first_seen_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    updated_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
