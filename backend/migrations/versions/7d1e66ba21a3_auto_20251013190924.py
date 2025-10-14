# migrations/versions/7d1e66ba21a3_auto_20251013190924.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# IDs из имени файла/логов – не трогаем
revision = "7d1e66ba21a3"
down_revision = "aa83ff84ceaf"
branch_labels = None
depends_on = None


def upgrade():
    # 1) чистим старые таблицы (если уже существуют)
    op.execute("DROP TABLE IF EXISTS file_versions CASCADE")
    op.execute("DROP TABLE IF EXISTS files CASCADE")

    # 2) создаём files с PK=BYTEA(32)
    op.create_table(
        "files",
        sa.Column("id", sa.LargeBinary(length=32), primary_key=True, nullable=False),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=True),
        sa.Column("cid", sa.Text(), nullable=False),
        sa.Column("checksum", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("checksum", "owner_id", name="uq_files_checksum_owner"),
    )
    op.create_index("ix_files_owner", "files", ["owner_id"])

    # 3) создаём file_versions с FK → files.id (BYTEA(32)) и снапшотом меты
    op.create_table(
        "file_versions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "file_id",
            sa.LargeBinary(length=32),
            sa.ForeignKey("files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("cid", sa.Text(), nullable=False),
        sa.Column("checksum", sa.LargeBinary(length=32), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("file_id", "version", name="uq_file_versions_file_version"),
    )
    op.create_index("ix_file_versions_file", "file_versions", ["file_id"])


def downgrade():
    op.drop_index("ix_file_versions_file", table_name="file_versions")
    op.drop_table("file_versions")
    op.drop_index("ix_files_owner", table_name="files")
    op.drop_table("files")
