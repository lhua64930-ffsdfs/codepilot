"""Record the exact workflow commit used for sandbox reproduction."""
from alembic import op
from sqlalchemy import Column, String, inspect

revision = "0002_ci_sandbox"
down_revision = "0001_reliability"
branch_labels = None
depends_on = None


def upgrade():
    if "head_sha" not in {col["name"] for col in inspect(op.get_bind()).get_columns("workflow_runs")}:
        op.add_column("workflow_runs", Column("head_sha", String(40), nullable=True))


def downgrade():
    op.drop_column("workflow_runs", "head_sha")
