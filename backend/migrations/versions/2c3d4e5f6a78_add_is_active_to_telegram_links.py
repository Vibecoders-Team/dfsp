"""Add is_active flag to telegram_links

Revision ID: 2c3d4e5f6a78
Revises: 1b2c3d4e5f67
Create Date: 2025-11-29 15:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2c3d4e5f6a78"
down_revision: Union[str, None] = "1b2c3d4e5f67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "telegram_links",
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    # Ensure only one active link per chat_id
    op.create_index(
        "uq_telegram_links_active_chat",
        "telegram_links",
        ["chat_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_telegram_links_active_chat", table_name="telegram_links")
    op.drop_column("telegram_links", "is_active")
