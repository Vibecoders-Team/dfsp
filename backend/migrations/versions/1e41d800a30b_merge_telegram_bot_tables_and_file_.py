"""merge telegram bot tables and file index migrations

Revision ID: 1e41d800a30b
Revises: 00674622c0ac, 090cff9666f1
Create Date: 2025-11-11 02:11:22.293139

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1e41d800a30b'
down_revision: Union[str, None] = ('00674622c0ac', '090cff9666f1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
