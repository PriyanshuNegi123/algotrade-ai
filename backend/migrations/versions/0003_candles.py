"""Immutable historical minute batches with catalog binding and UTC bars."""

import sqlalchemy as sa
from alembic import op

revision = "0003_candles"
down_revision = "0002_instruments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "candle_imports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=False),
        sa.Column("instrument_type", sa.String(8), nullable=False),
        sa.Column("interval", sa.Integer(), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("response_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_sha256", sa.String(64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("gap_count", sa.Integer(), nullable=False),
        sa.Column("source_order", sa.String(16), nullable=False),
        sa.Column("canonical_payload", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "instrument_key"],
            ["instruments.snapshot_id", "instruments.instrument_key"],
        ),
        sa.CheckConstraint("interval IN (1,5,15)", name="ck_candle_interval"),
        sa.CheckConstraint("row_count >= 0 AND gap_count >= 0", name="ck_candle_counts"),
    )
    op.create_index("ix_candle_imports_imported_at", "candle_imports", ["imported_at"])
    op.create_table(
        "candles",
        sa.Column("import_id", sa.String(64), sa.ForeignKey("candle_imports.id"), primary_key=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        *(
            sa.Column(name, sa.Numeric(24, 8), nullable=False)
            for name in ("open", "high", "low", "close")
        ),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("open_interest", sa.BigInteger()),
        sa.CheckConstraint(
            "low > 0 AND high >= low AND open >= low AND open <= high "
            "AND close >= low AND close <= high",
            name="ck_candle_ohlc",
        ),
        sa.CheckConstraint(
            "volume >= 0 AND (open_interest IS NULL OR open_interest >= 0)", name="ck_candle_volume"
        ),
        sa.CheckConstraint("closed_at > opened_at", name="ck_candle_times"),
    )


def downgrade():
    op.drop_table("candles")
    op.drop_index("ix_candle_imports_imported_at", "candle_imports")
    op.drop_table("candle_imports")
