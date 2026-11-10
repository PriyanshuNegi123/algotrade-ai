"""Opt-in popup OAuth: anonymous return page, authenticated origin/CSRF/binding finish."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.auth.service import require_admin
from backend.app.brokers.oauth import (
    OAuthApp,
    OAuthError,
    OAuthToken,
    UpstoxOAuth,
    app_digest,
    configured_app,
    utc_now,
)
from backend.app.brokers.oauth_browser import OAuthBrowserFlows, callback_configuration
from backend.app.brokers.oauth_store import OAuthStoreError, OAuthTokenStore
from backend.app.config import Settings
from backend.app.database import AdminSession

FRONTEND = Path(__file__).resolve().parents[3] / "frontend"


class FinishInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    state: SecretStr = Field(min_length=43, max_length=43)
    flow_nonce: SecretStr = Field(min_length=43, max_length=43)
    code: SecretStr | None = Field(default=None, max_length=8192)
    denied: bool = Field(default=False, strict=True)


def components(settings: Settings) -> tuple[OAuthApp, str, str, OAuthTokenStore]:
    app = configured_app(settings)
    path, origin = callback_configuration(app, settings.allowed_origins)
    directory = Path(settings.upstox_oauth_vault_dir)
    if (
        not settings.upstox_oauth_vault_dir
        or not directory.is_absolute()
        or settings.trading_mode != "OBSERVATION"
        or settings.live_enabled is not False
    ):
        raise OAuthError("OAUTH_LOCAL_SETUP_REQUIRED")
    return app, path, origin, OAuthTokenStore(directory)


def session_expiry(engine: Engine, identity: str) -> datetime:
    with Session(engine) as db:
        row = db.get(AdminSession, identity)
        if row is None:
            raise HTTPException(401, "Administrator session expired or revoked")
        expiry = row.expires_at
        expiry = expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry
        if expiry <= utc_now():
            raise HTTPException(401, "Administrator session expired or revoked")
        return expiry


def persist_for_active_session(
    engine: Engine,
    identity: str,
    store: OAuthTokenStore,
    app: OAuthApp,
    token: OAuthToken,
    flows: OAuthBrowserFlows,
    state: SecretStr,
) -> None:
    # Serialize the final authorization point with concurrent logout/session revocation.
    with Session(engine) as db, db.begin():
        if engine.dialect.name == "postgresql":
            db.execute(text("SET LOCAL lock_timeout = '1000ms'"))
            db.execute(text("SET LOCAL statement_timeout = '2000ms'"))
        row = db.scalar(
            select(AdminSession).where(AdminSession.token_digest == identity).with_for_update()
        )
        if row is None:
            raise HTTPException(401, "Administrator session expired or revoked")
        expiry = row.expires_at
        expiry = expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry
        if expiry <= utc_now():
            raise HTTPException(401, "Administrator session expired or revoked")
        with flows.finalize(identity, state):
            store.save(app, token)


def safe_error(error: OAuthError) -> HTTPException:
    code = str(error)
    allowed = {
        "OAUTH_BROWSER_BINDING_INVALID",
        "OAUTH_APP_CHANGED",
        "OAUTH_AUTHORIZATION_DENIED",
        "OAUTH_STATE_INVALID",
        "OAUTH_STATE_EXPIRED",
        "OAUTH_SESSION_EXPIRED",
        "OAUTH_SESSION_MISMATCH",
        "OAUTH_CODE_INVALID",
        "OAUTH_TOKEN_REQUEST_REJECTED",
        "OAUTH_TOKEN_RESPONSE_INVALID",
        "OAUTH_TOKEN_RESPONSE_TOO_LARGE",
        "OAUTH_EXPIRED_DURING_EXCHANGE",
        "OAUTH_RATE_LIMITED",
        "OAUTH_TOKEN_SERVICE_UNAVAILABLE",
        "OAUTH_PENDING_LIMIT",
        "OAUTH_CLOCK_INVALID",
        "OAUTH_STATE_SUPERSEDED",
    }
    detail = code if code in allowed else "OAUTH_UNAVAILABLE"
    status = (
        429
        if code in {"OAUTH_RATE_LIMITED", "OAUTH_PENDING_LIMIT"}
        else (503 if code == "OAUTH_TOKEN_SERVICE_UNAVAILABLE" else 400)
    )
    return HTTPException(status, detail)


def build_router(settings: Settings) -> tuple[APIRouter, list[str]]:
    router = APIRouter()
    callbacks: list[str] = []
    try:
        _, path, _, _ = components(settings)
        callbacks.append(path)
    except OAuthError:
        pass  # Missing/invalid optional OAuth must not disable the Analytics application.

    @router.get("/api/broker/oauth/status")
    def status(
        request: Request, identity: Annotated[str, Depends(require_admin)]
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "state": "LOCAL_SETUP_REQUIRED",
            "can_start": False,
            "vault_state": "NOT_CHECKED",
            "broker_access_verified": False,
            "entries_enabled": False,
            "live_enabled": False,
        }
        try:
            app, _, _, store = components(request.app.state.settings)
            vault = store.status(app)
            state = vault["state"]
            ready = state in {
                "STORED_UNVERIFIED",
                "OAUTH_VAULT_NOT_INITIALIZED",
                "OAUTH_VAULT_TOKEN_EXPIRED",
            }
            result.update(
                state="STORED_UNVERIFIED"
                if state == "STORED_UNVERIFIED"
                else "READY_FOR_AUTHORIZATION"
                if ready
                else "STORAGE_UNAVAILABLE",
                can_start=ready,
                vault_state=state,
            )
        except OAuthError:
            pass
        return result

    @router.post("/api/broker/oauth/start")
    def start(request: Request, identity: Annotated[str, Depends(require_admin)]) -> dict[str, Any]:
        try:
            app, _, origin, store = components(request.app.state.settings)
        except OAuthError:
            raise HTTPException(503, "OAUTH_LOCAL_SETUP_REQUIRED") from None
        if request.headers.get("origin") != origin:
            raise HTTPException(403, "OAUTH_CALLBACK_ORIGIN_MISMATCH")
        expiry = session_expiry(request.app.state.engine, identity)
        try:
            store.prepare(app)  # Explicit authorized start prepares storage before broker consent.
            authorization, state, nonce = cast(
                OAuthBrowserFlows, request.app.state.oauth_flows
            ).begin(
                app,
                identity,
                expiry,
                storage_context=request.app.state.settings.upstox_oauth_vault_dir,
            )
        except OAuthStoreError:
            raise HTTPException(503, "OAUTH_STORAGE_UNAVAILABLE") from None
        except OAuthError as error:
            raise safe_error(error) from None
        return {
            "authorization_url": authorization.url.get_secret_value(),
            "state": state.get_secret_value(),
            "flow_nonce": nonce.get_secret_value(),
            "expires_at": authorization.expires_at,
            "entries_enabled": False,
            "live_enabled": False,
        }

    @router.post("/api/broker/oauth/finish")
    async def finish(
        payload: FinishInput, request: Request, identity: Annotated[str, Depends(require_admin)]
    ) -> dict[str, Any]:
        try:
            app, _, origin, store = components(request.app.state.settings)
        except OAuthError:
            raise HTTPException(503, "OAUTH_LOCAL_SETUP_REQUIRED") from None
        if request.headers.get("origin") != origin:
            raise HTTPException(403, "OAUTH_CALLBACK_ORIGIN_MISMATCH")
        vault_location = request.app.state.settings.upstox_oauth_vault_dir
        flows = cast(OAuthBrowserFlows, request.app.state.oauth_flows)
        try:
            token = await flows.finish(
                app,
                cast(UpstoxOAuth, request.app.state.oauth_client),
                identity,
                payload.state,
                payload.flow_nonce,
                payload.code,
                denied=payload.denied,
                storage_context=vault_location,
            )
            latest_app, _, latest_origin, _ = components(request.app.state.settings)
            if (
                app_digest(latest_app) != app_digest(app)
                or latest_origin != origin
                or request.app.state.settings.upstox_oauth_vault_dir != vault_location
            ):
                raise OAuthError("OAUTH_APP_CHANGED")
            await asyncio.to_thread(
                persist_for_active_session,
                request.app.state.engine,
                identity,
                store,
                app,
                token,
                flows,
                payload.state,
            )
        except OAuthStoreError:
            raise HTTPException(503, "OAUTH_STORAGE_UNAVAILABLE") from None
        except OAuthError as error:
            if str(error) == "OAUTH_AUTHORIZATION_DENIED":
                return {
                    "state": "AUTHORIZATION_DENIED",
                    "broker_access_verified": False,
                    "entries_enabled": False,
                    "live_enabled": False,
                }
            raise safe_error(error) from None
        finally:
            await asyncio.to_thread(flows.discard_consumed, identity, payload.state)
        return {
            "state": "STORED_UNVERIFIED",
            "broker_access_verified": False,
            "entries_enabled": False,
            "live_enabled": False,
        }

    if callbacks:

        @router.get(callbacks[0], include_in_schema=False)
        def callback() -> FileResponse:
            # No cookie, code parsing, token exchange or credential persistence on GET.
            return FileResponse(FRONTEND / "oauth-callback.html", headers={"Pragma": "no-cache"})

    return router, callbacks
