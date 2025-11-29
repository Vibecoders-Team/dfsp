"""add ton_pubkey to users

Revision ID: 6f7a8b9c0d12
Revises: 4e5f6a7b8c90
Create Date: 2025-11-29 17:55:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6f7a8b9c0d12"
down_revision: Union[str, None] = "4e5f6a7b8c90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ton_pubkey", sa.LargeBinary(), nullable=True))
    op.create_index("ix_users_ton_pubkey", "users", ["ton_pubkey"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_ton_pubkey", table_name="users")
    op.drop_column("users", "ton_pubkey")
