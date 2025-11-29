from alembic import op
import sqlalchemy as sa

revision = "4b6b76f5fcd1"
down_revision = "7d1e66ba21a3"
branch_labels = None
depends_on = None

def upgrade():
    # no-op — схема уже пересоздана в 7d1e66
    pass

def downgrade():
    pass
