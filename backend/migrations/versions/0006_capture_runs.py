"""Bounded capture parent ledger; preserve all standalone observation data."""

import sqlalchemy as sa
from alembic import op

revision = "0006_capture_runs"
down_revision = "0005_observations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "capture_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("requested_keys", sa.JSON(), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(40)),
        *(
            sa.Column(name, sa.DateTime(timezone=True), nullable=False)
            for name in ("created_at", "lease_expires_at")
        ),
        *(sa.Column(name, sa.DateTime(timezone=True)) for name in ("ended_at", "recovered_at")),
        sa.Column("session_count", sa.Integer(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("payload_bytes", sa.BigInteger(), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.CheckConstraint("source IN ('UPSTOX_V3','SYNTHETIC')", name="ck_capture_source"),
        sa.CheckConstraint(
            "status IN ('RUNNING','CLOSED','INTERRUPTED')", name="ck_capture_status"
        ),
        sa.CheckConstraint(
            "session_count >= 0 AND session_count <= 12 AND event_count >= 0 "
            "AND event_count <= 100000 AND payload_bytes >= 0 AND payload_bytes <= 67108864",
            name="ck_capture_bounds",
        ),
    )
    for name in ("created_at", "lease_expires_at"):
        op.create_index(f"ix_capture_runs_{name}", "capture_runs", [name])
    with op.batch_alter_table("observation_sessions") as batch:
        batch.add_column(sa.Column("supervisor_id", sa.String(32)))
        batch.create_foreign_key(
            "fk_observation_supervisor", "capture_runs", ["supervisor_id"], ["id"]
        )
        batch.create_index("ix_observation_sessions_supervisor_id", ["supervisor_id"])


def downgrade():
    with op.batch_alter_table("observation_sessions") as batch:
        batch.drop_index("ix_observation_sessions_supervisor_id")
        batch.drop_constraint("fk_observation_supervisor", type_="foreignkey")
        batch.drop_column("supervisor_id")
    for name in ("created_at", "lease_expires_at"):
        op.drop_index(f"ix_capture_runs_{name}", "capture_runs")
    op.drop_table("capture_runs")
