"""Adopt existing demo schemas without destructive cleanup; create reliability tables."""
from alembic import op
from app.db.schema import upgrade_schema

revision = "0001_reliability"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    upgrade_schema(op.get_bind())


def downgrade():
    raise RuntimeError("This baseline cannot be downgraded automatically. Restore a database backup instead.")
