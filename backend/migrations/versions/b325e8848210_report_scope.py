"""Preserve the report authorization scope after a user's role changes."""
from alembic import op
import sqlalchemy as sa

revision = "b325e8848210"
down_revision = "bf4807733e43"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reports", sa.Column("scope", sa.String(16), nullable=False, server_default="own"))
    # Existing requester roles determine scope for artifacts made pre-migration.
    op.execute("UPDATE reports SET scope='organization' WHERE user_id IN (SELECT id FROM users WHERE role IN ('admin','analyst'))")


def downgrade():
    op.drop_column("reports", "scope")
