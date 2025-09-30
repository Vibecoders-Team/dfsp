from datetime import datetime
from sqlalchemy import ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
import uuid

class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("checksum", "owner_id", name="uq_files_checksum_owner"),
        Index("ix_files_owner", "owner_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str]
    size: Mapped[int]
    mime: Mapped[str | None]
    cid: Mapped[str]                # IPFS CID
    checksum: Mapped[bytes]         # 32 bytes (base64 в API, в БД — bytea)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class FileVersion(Base):
    __tablename__ = "file_versions"
    __table_args__ = (
        UniqueConstraint("file_id", "version", name="uq_file_versions_file_version"),
        Index("ix_file_versions_file", "file_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    version: Mapped[int]           # 1..N
    cid: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
