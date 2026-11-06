"""Durable opaque administrator sessions. No broker credentials stored."""

import sqlalchemy as sa
from alembic import op

revision = "0001_sessions"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admin_sessions",
        sa.Column("token_digest", sa.String(64), primary_key=True),
        sa.Column("csrf_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])


def downgrade():
    op.drop_index("ix_admin_sessions_expires_at", "admin_sessions")
    op.drop_table("admin_sessions")
