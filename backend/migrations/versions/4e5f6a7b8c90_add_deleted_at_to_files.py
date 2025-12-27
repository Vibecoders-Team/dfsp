"""add deleted_at to files

Revision ID: 4e5f6a7b8c90
Revises: 3d4e5f6a7b89
Create Date: 2025-11-29 16:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "4e5f6a7b8c90"
down_revision: Union[str, None] = "3d4e5f6a7b89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("files", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_files_deleted_at", "files", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_files_deleted_at", table_name="files")
    op.drop_column("files", "deleted_at")
