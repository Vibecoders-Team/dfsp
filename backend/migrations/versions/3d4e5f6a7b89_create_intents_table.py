"""create intents table

Revision ID: 3d4e5f6a7b89
Revises: 2c3d4e5f6a78
Create Date: 2025-11-29 16:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3d4e5f6a7b89"
down_revision: Union[str, None] = "2c3d4e5f6a78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_intents_expires_at", "intents", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_intents_expires_at", table_name="intents")
    op.drop_table("intents")
