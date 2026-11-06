"""Catalog-bound option-chain receipt snapshots and sanitized quote legs."""

import sqlalchemy as sa
from alembic import op

revision = "0004_option_chain"
down_revision = "0003_candles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "option_chain_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("catalog_snapshot_id", sa.String(64), nullable=False),
        sa.Column("underlying_key", sa.String(160), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("response_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_sha256", sa.String(64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strike_count", sa.Integer(), nullable=False),
        sa.Column("leg_count", sa.Integer(), nullable=False),
        sa.Column("flagged_legs", sa.Integer(), nullable=False),
        sa.Column("canonical_payload", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_snapshot_id", "underlying_key"],
            ["instruments.snapshot_id", "instruments.instrument_key"],
        ),
        sa.CheckConstraint(
            "strike_count >= 0 AND leg_count = 2 * strike_count AND flagged_legs >= 0",
            name="ck_chain_counts",
        ),
    )
    for name in ("retrieved_at", "imported_at"):
        op.create_index(f"ix_option_chain_snapshots_{name}", "option_chain_snapshots", [name])
    op.create_table(
        "option_chain_legs",
        sa.Column(
            "snapshot_id",
            sa.String(64),
            sa.ForeignKey("option_chain_snapshots.id"),
            primary_key=True,
        ),
        sa.Column("instrument_key", sa.String(160), primary_key=True),
        sa.Column("catalog_snapshot_id", sa.String(64), nullable=False),
        sa.Column("option_type", sa.String(2), nullable=False),
        sa.Column("strike_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("underlying_spot", sa.Numeric(24, 8)),
        sa.Column("pcr", sa.Numeric(30, 16)),
        *(
            sa.Column(name, sa.Numeric(24, 8))
            for name in ("ltp", "close_price", "bid_price", "ask_price", "spread")
        ),
        *(
            sa.Column(name, sa.BigInteger())
            for name in ("bid_qty", "ask_qty", "volume", "oi", "prev_oi")
        ),
        sa.Column("greeks", sa.JSON(), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_snapshot_id", "instrument_key"],
            ["instruments.snapshot_id", "instruments.instrument_key"],
        ),
        sa.CheckConstraint(
            "option_type IN ('CE','PE') AND strike_price > 0 AND lot_size > 0",
            name="ck_chain_identity",
        ),
        sa.CheckConstraint(
            "(bid_price IS NULL OR bid_price >= 0) AND (ask_price IS NULL OR ask_price >= 0)",
            name="ck_chain_prices",
        ),
        sa.CheckConstraint(
            "bid_price IS NULL OR ask_price IS NULL OR bid_price = 0 "
            "OR ask_price = 0 OR bid_price <= ask_price",
            name="ck_chain_spread",
        ),
    )


def downgrade():
    op.drop_table("option_chain_legs")
    for name in ("retrieved_at", "imported_at"):
        op.drop_index(f"ix_option_chain_snapshots_{name}", "option_chain_snapshots")
    op.drop_table("option_chain_snapshots")
