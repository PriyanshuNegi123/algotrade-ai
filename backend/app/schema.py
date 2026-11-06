"""Shared read-only runtime schema probes; never run migrations during a check."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.database import SCHEMA_REVISION

PROBES = (
    ("admin_sessions", "token_digest"),
    ("instrument_snapshots", "id"),
    ("instruments", "snapshot_id"),
    ("candle_imports", "id"),
    ("candles", "import_id"),
    ("option_chain_snapshots", "id"),
    ("option_chain_legs", "snapshot_id"),
    ("observation_sessions", "supervisor_id"),
    ("capture_runs", "id"),
    ("observation_attempts", "session_id"),
    ("observation_events", "sequence"),
)


class SchemaMismatch(Exception):
    pass


def verify_schema(connection: Connection) -> None:
    revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    if revision != SCHEMA_REVISION:
        raise SchemaMismatch("SCHEMA_REVISION_MISMATCH")
    for table, column in PROBES:  # Identifiers are fixed source constants, never caller inputs.
        connection.execute(text(f"SELECT {column} FROM {table} LIMIT 0"))
