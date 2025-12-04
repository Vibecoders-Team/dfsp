"""create public_links table

Revision ID: c7a4c2b8e3f4
Revises: 850f302dfa93
Create Date: 2025-10-31 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7a4c2b8e3f4"
down_revision: Union[str, None] = "7a8b9c0d1e23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "public_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", sa.LargeBinary(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_downloads", sa.Integer(), nullable=True),
        sa.Column("downloads_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("pow_difficulty", sa.SmallInteger(), nullable=True),
        sa.Column("bandwidth_mb_per_day", sa.Integer(), nullable=True),
        sa.Column("one_time", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("snapshot_name", sa.Text(), nullable=False),
        sa.Column("snapshot_mime", sa.Text(), nullable=True),
        sa.Column("snapshot_size", sa.BigInteger(), nullable=True),
        sa.Column("snapshot_cid", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="ux_public_links_token"),
    )
    op.create_index("ix_public_links_file_id", "public_links", ["file_id"], unique=False)
    op.create_index("ix_public_links_expires_at", "public_links", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_public_links_expires_at", table_name="public_links")
    op.drop_index("ix_public_links_file_id", table_name="public_links")
    op.drop_table("public_links")
