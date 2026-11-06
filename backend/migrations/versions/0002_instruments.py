"""Immutable public instrument source archives and per-snapshot metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0002_instruments"
down_revision = "0001_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instrument_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_url", sa.String(256), nullable=False),
        sa.Column("source_modified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("source_records", sa.Integer(), nullable=False),
        sa.Column("selected_records", sa.Integer(), nullable=False),
        sa.Column("raw_gzip", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint(
            "source_records > 0 AND selected_records > 0", name="ck_snapshot_counts"
        ),
    )
    op.create_index(
        "ix_instrument_snapshots_retrieved_at", "instrument_snapshots", ["retrieved_at"]
    )
    op.create_index("ix_instrument_snapshots_imported_at", "instrument_snapshots", ["imported_at"])
    op.create_table(
        "instruments",
        sa.Column(
            "snapshot_id", sa.String(64), sa.ForeignKey("instrument_snapshots.id"), primary_key=True
        ),
        sa.Column("instrument_key", sa.String(160), primary_key=True),
        sa.Column("segment", sa.String(16), nullable=False),
        sa.Column("instrument_type", sa.String(8), nullable=False),
        sa.Column("trading_symbol", sa.String(160), nullable=False),
        sa.Column("underlying_key", sa.String(160)),
        sa.Column("lot_size", sa.Integer()),
        sa.Column("minimum_lot", sa.Integer()),
        sa.Column("tick_size_raw", sa.Numeric(24, 8)),
        sa.Column("tick_size_unit", sa.String(32), nullable=False),
        sa.Column("expiry", sa.DateTime(timezone=True)),
        sa.Column("strike_price", sa.Numeric(24, 8)),
        sa.CheckConstraint(
            "instrument_type IN ('INDEX','CE','PE','FUT')", name="ck_instrument_type"
        ),
        sa.CheckConstraint("lot_size IS NULL OR lot_size > 0", name="ck_instrument_lot"),
        sa.CheckConstraint("tick_size_raw IS NULL OR tick_size_raw > 0", name="ck_instrument_tick"),
    )
    op.create_index(
        "ix_instrument_contracts",
        "instruments",
        [
            "snapshot_id",
            "underlying_key",
            "instrument_type",
            "expiry",
        ],
    )


def downgrade():
    op.drop_index("ix_instrument_contracts", "instruments")
    op.drop_table("instruments")
    op.drop_index("ix_instrument_snapshots_imported_at", "instrument_snapshots")
    op.drop_index("ix_instrument_snapshots_retrieved_at", "instrument_snapshots")
    op.drop_table("instrument_snapshots")
