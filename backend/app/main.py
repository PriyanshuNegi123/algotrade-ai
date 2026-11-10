import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.api.broker import router as broker_router
from backend.app.api.candles import HistoryGate
from backend.app.api.candles import router as candle_router
from backend.app.api.instruments import ImportGate
from backend.app.api.instruments import router as instrument_router
from backend.app.api.oauth import build_router as build_oauth_router
from backend.app.api.observations import router as observation_router
from backend.app.api.option_chain import ChainGate
from backend.app.api.option_chain import router as chain_router
from backend.app.auth.service import (
    LoginLimiter,
    create_session,
    require_admin,
    require_origin,
    verify_password,
)
from backend.app.brokers.oauth import UpstoxOAuth
from backend.app.brokers.oauth_browser import OAuthBrowserFlows
from backend.app.brokers.upstox import BrokerMonitor, ReadOnlyUpstox
from backend.app.config import Settings
from backend.app.database import AdminSession, build_engine
from backend.app.schema import SchemaMismatch, verify_schema
from backend.app.security.logging import configure_logging
from backend.app.security.oauth_privacy import OAuthPrivacyMiddleware

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: SecretStr = Field(min_length=12, max_length=256)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        yield
        app.state.engine.dispose()

    app = FastAPI(
        title="AlgoTrade AI",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = config
    app.state.engine = build_engine(config)
    app.state.limiter = LoginLimiter()
    app.state.broker_monitor = BrokerMonitor(ReadOnlyUpstox(config))
    app.state.oauth_flows = OAuthBrowserFlows()
    app.state.oauth_client = UpstoxOAuth()
    oauth_router, oauth_callbacks = build_oauth_router(config)
    app.include_router(oauth_router)
    app.include_router(broker_router)
    app.state.instrument_gate = ImportGate()
    app.include_router(instrument_router)
    app.state.history_gate = HistoryGate()
    app.include_router(candle_router)
    app.state.chain_gate = ChainGate()
    app.include_router(chain_router)
    app.include_router(observation_router)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts)
    app.add_middleware(OAuthPrivacyMiddleware, callback_paths=oauth_callbacks)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        request_id = secrets.token_hex(12)
        try:
            response: Response = await call_next(request)
        except Exception:
            response = JSONResponse({"detail": "Internal service error"}, status_code=500)
        response.headers.update(
            {
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self'; connect-src 'self'; object-src 'none'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Cache-Control": "no-store",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "X-Request-ID": request_id,
            }
        )
        if config.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        logging.getLogger("algotrade").info(
            "request_complete", extra={"request_id": request_id, "status": response.status_code}
        )
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse({"detail": "Database unavailable"}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default validation payload can echo submitted secret fields.
        return JSONResponse({"detail": "Invalid request payload"}, status_code=422)

    @app.get("/health/live")
    def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    def readiness() -> JSONResponse:
        try:
            with app.state.engine.connect() as connection:
                verify_schema(connection)
        except (SQLAlchemyError, ValueError, SchemaMismatch):
            return JSONResponse({"status": "not_ready", "entries_enabled": False}, status_code=503)
        ready = bool(config.admin_password_hash.get_secret_value())
        return JSONResponse(
            {"status": "ready" if ready else "not_ready", "entries_enabled": False},
            status_code=200 if ready else 503,
        )

    @app.post("/api/auth/login")
    def login(payload: LoginInput, request: Request, response: Response) -> dict[str, str]:
        require_origin(request)
        app.state.limiter.check()
        encoded = config.admin_password_hash.get_secret_value()
        if not encoded:
            raise HTTPException(503, "Administrator authentication is not configured")
        if not verify_password(payload.password.get_secret_value(), encoded):
            raise HTTPException(401, "Invalid credentials")
        token, csrf = create_session(request)
        response.set_cookie(
            "admin_session",
            token,
            httponly=True,
            secure=config.cookie_secure,
            samesite="strict",
            max_age=config.session_minutes * 60,
            path="/",
        )
        return {"csrf_token": csrf}

    @app.post("/api/auth/logout", status_code=204)
    def logout(response: Response, token: Annotated[str, Depends(require_admin)]) -> None:
        with Session(app.state.engine) as db:
            db.execute(delete(AdminSession).where(AdminSession.token_digest == token))
            db.commit()
        response.delete_cookie(
            "admin_session", secure=config.cookie_secure, httponly=True, samesite="strict", path="/"
        )

    @app.get("/api/overview", dependencies=[Depends(require_admin)])
    def overview() -> dict[str, Any]:
        return {
            "mode": config.trading_mode,
            "entries_enabled": False,
            "live_enabled": False,
            "phase": "Read-only broker foundation",
            "broker_status": app.state.broker_monitor.snapshot().state,
            "data_status": "No market data connected",
            "observation_days": 7,
            "observation_started_at": None,
            "balance": None,
            "available_capital": None,
            "starting_equity": None,
            "realized_pnl": None,
            "unrealized_pnl": None,
            "trading_costs": None,
            "daily_pnl": None,
            "monthly_pnl": None,
            "max_drawdown": None,
            "positions": [],
            "decisions": [],
            "position_stop_loss_percent": 35,
            "account_drawdown_percent": 35,
            "risk_enforcement": "Not implemented; all execution unavailable",
            "next_action": app.state.broker_monitor.snapshot().next_action,
        }

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND / "index.html")

    app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")
    return app


# Factory startup: uvicorn backend.app.main:create_app --factory
