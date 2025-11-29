"""Add telegram_links table

Revision ID: 1b2c3d4e5f67
Revises: 00674622c0ac
Create Date: 2025-11-29 13:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1b2c3d4e5f67"
down_revision: Union[str, None] = "00674622c0ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_links",
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("wallet_address", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("chat_id", "wallet_address"),
    )
    op.create_index(
        "ix_telegram_links_chat_revoked_created",
        "telegram_links",
        ["chat_id", "revoked_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_links_wallet_revoked",
        "telegram_links",
        ["wallet_address", "revoked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_links_wallet_revoked", table_name="telegram_links")
    op.drop_index("ix_telegram_links_chat_revoked_created", table_name="telegram_links")
    op.drop_table("telegram_links")
