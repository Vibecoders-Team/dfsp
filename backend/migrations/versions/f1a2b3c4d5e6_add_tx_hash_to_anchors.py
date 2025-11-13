"""add tx_hash to anchors

Revision ID: f1a2b3c4d5e6
Revises: 850f302dfa93
Create Date: 2025-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = '850f302dfa93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tx_hash column to anchors table
    op.add_column('anchors', sa.Column('tx_hash', sa.String(length=66), nullable=True))


def downgrade() -> None:
    # Remove tx_hash column from anchors table
    op.drop_column('anchors', 'tx_hash')

