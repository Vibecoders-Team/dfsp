from datetime import datetime
from sqlalchemy import ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
import uuid

class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (
        Index("ix_grants_grantee", "grantee_id"),
        Index("ix_grants_file", "file_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    grantee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    ttl_days: Mapped[int | None]
    max_dl: Mapped[int | None]
    used: Mapped[int] = mapped_column(default=0)
    enc_k: Mapped[str | None]      # зашифрованный ключ для конкретного получателя
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
