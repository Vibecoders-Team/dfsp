import uuid
from datetime import datetime
from sqlalchemy import func, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class User(Base):
    """
    Database model for user accounts, using SQLAlchemy 2.0 style.
    Users are identified by their Ethereum address and store their RSA public key.
    """

    __tablename__ = "users"

    # Primary key: UUID
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)

    # Ethereum Address: Unique and required (42 chars max: '0x' + 40 hex)
    eth_address: Mapped[str] = mapped_column(String(42), unique=True, index=True)

    # RSA Public Key (PEM SPKI format) - Required for registration
    rsa_public_spki_pem: Mapped[str]

    # Display name (optional)
    display_name: Mapped[str | None]

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Updated timestamp: automatically set on update
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self):
        return f"<User(id={self.id}, eth_address='{self.eth_address}')>"
