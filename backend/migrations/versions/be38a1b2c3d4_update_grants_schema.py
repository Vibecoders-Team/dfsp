# migrations/versions/be38a1b2c3d4_update_grants_schema.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "be38a1b2c3d4"
down_revision = "4b6b76f5fcd1"
branch_labels = None
depends_on = None


def upgrade():
    # Recreate grants table to align with Sprint 2 schema.
    # NOTE: This will drop existing data in dev environments.
    op.execute("DROP TABLE IF EXISTS grants CASCADE")

    op.create_table(
        "grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("cap_id", sa.LargeBinary(length=32), nullable=False),
        sa.Column("file_id", sa.LargeBinary(length=32), nullable=False),  # FK → files.id (BYTEA(32))
        sa.Column("grantor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grantee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_dl", sa.Integer(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("tx_hash", sa.String(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enc_key", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("cap_id", name="uq_grants_cap_id"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["grantor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["grantee_id"], ["users.id"], ondelete="RESTRICT"),
    )

    op.create_index("ix_grants_file", "grants", ["file_id"], unique=False)
    op.create_index("ix_grants_grantee", "grants", ["grantee_id"], unique=False)
    op.create_index("ix_grants_grantee_expires", "grants", ["grantee_id", "expires_at"], unique=False)


def downgrade():
    op.drop_index("ix_grants_grantee_expires", table_name="grants")
    op.drop_index("ix_grants_grantee", table_name="grants")
    op.drop_index("ix_grants_file", table_name="grants")
    op.drop_table("grants")

