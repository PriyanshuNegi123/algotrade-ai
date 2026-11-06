from alembic import context

from backend.app.config import Settings
from backend.app.database import Base, build_engine
from backend.app.instruments.models import Instrument, InstrumentSnapshot  # noqa: F401
from backend.app.market_data.models import Candle, CandleImport  # noqa: F401
from backend.app.market_data.observation_models import (  # noqa: F401
    ObservationAttempt,
    ObservationEvent,
    ObservationSession,
)
from backend.app.market_data.option_models import ChainLeg, ChainSnapshot  # noqa: F401
from backend.app.market_data.supervision_models import CaptureRun  # noqa: F401

settings = Settings()
if context.is_offline_mode():
    context.configure(
        url=settings.database_url.get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = build_engine(settings)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
