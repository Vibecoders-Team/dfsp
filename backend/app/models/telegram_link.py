from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import BIGINT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TelegramLink(Base):
    __tablename__ = "telegram_links"

    chat_id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    wallet_address: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false(), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    flags: Mapped[dict] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False)

    def __repr__(self) -> str:
        return f"<TelegramLink(chat_id={self.chat_id}, wallet_address='{self.wallet_address}')>"
