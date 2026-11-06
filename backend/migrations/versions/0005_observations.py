"""Bounded research observation sessions, catalog attempts and canonical events."""

import sqlalchemy as sa
from alembic import op

revision = "0005_observations"
down_revision = "0004_option_chain"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "observation_sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("schema_sha256", sa.String(64), nullable=False),
        sa.Column("requested_keys", sa.JSON(), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(64)),
        *(
            sa.Column(name, sa.DateTime(timezone=True), nullable=False)
            for name in ("created_at", "lease_expires_at")
        ),
        *(sa.Column(name, sa.DateTime(timezone=True)) for name in ("ended_at", "recovered_at")),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("payload_bytes", sa.BigInteger(), nullable=False),
        sa.Column("last_elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("run_elapsed_ms", sa.Integer()),
        sa.Column("observed_interval_ms", sa.Integer(), nullable=False),
        sa.Column("previous_sample", sa.JSON()),
        sa.CheckConstraint("source IN ('UPSTOX_V3','SYNTHETIC')", name="ck_observation_source"),
        sa.CheckConstraint(
            "status IN ('RUNNING','CLOSED','INTERRUPTED')", name="ck_observation_status"
        ),
        sa.CheckConstraint(
            "event_count >= 0 AND event_count <= 11000 AND payload_bytes >= 0 "
            "AND payload_bytes <= 33554432 AND observed_interval_ms >= 0 "
            "AND last_elapsed_ms >= 0",
            name="ck_observation_bounds",
        ),
    )
    for name in ("created_at", "lease_expires_at"):
        op.create_index(f"ix_observation_sessions_{name}", "observation_sessions", [name])
    op.create_table(
        "observation_attempts",
        sa.Column(
            "session_id", sa.String(32), sa.ForeignKey("observation_sessions.id"), primary_key=True
        ),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column(
            "catalog_snapshot_id",
            sa.String(64),
            sa.ForeignKey("instrument_snapshots.id"),
            nullable=False,
        ),
        sa.Column("instrument_keys", sa.JSON(), nullable=False),
        sa.CheckConstraint("number >= 1 AND number <= 3", name="ck_observation_attempt"),
    )
    op.create_table(
        "observation_events",
        sa.Column("session_id", sa.String(32), primary_key=True),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "attempt"],
            ["observation_attempts.session_id", "observation_attempts.number"],
        ),
        sa.UniqueConstraint("session_id", "payload_sha256", name="uq_observation_receipt"),
        sa.CheckConstraint("sequence > 0 AND elapsed_ms >= 0", name="ck_observation_event"),
    )


def downgrade():
    op.drop_table("observation_events")
    op.drop_table("observation_attempts")
    for name in ("created_at", "lease_expires_at"):
        op.drop_index(f"ix_observation_sessions_{name}", "observation_sessions")
    op.drop_table("observation_sessions")
