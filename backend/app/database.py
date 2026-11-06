from datetime import datetime

from sqlalchemy import DateTime, String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.app.config import Settings

SCHEMA_REVISION = "0006_capture_runs"


class Base(DeclarativeBase):
    pass


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    token_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def build_engine(settings: Settings) -> Engine:
    url = settings.database_url.get_secret_value()
    options = {"connect_args": {"connect_timeout": 3}} if url.startswith("postgresql") else {}
    return create_engine(url, pool_pre_ping=True, hide_parameters=True, **options)
