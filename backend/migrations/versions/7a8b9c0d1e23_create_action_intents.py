"""create action_intents table

Revision ID: 7a8b9c0d1e23
Revises: 6f7a8b9c0d12
Create Date: 2025-11-29 18:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7a8b9c0d1e23"
down_revision: Union[str, None] = "6f7a8b9c0d12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "action_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("owner_address", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_action_intents_owner", "action_intents", ["owner_address"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_action_intents_owner", table_name="action_intents")
    op.drop_table("action_intents")
