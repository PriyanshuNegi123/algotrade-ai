import hashlib
import secrets
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.database import AdminSession

hasher = PasswordHasher()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class LoginLimiter:
    """Global bounded limiter for a single-process administrator-only deployment."""

    def __init__(self) -> None:
        self.attempts: deque[float] = deque()
        self.lock = threading.Lock()

    def check(self) -> None:
        with self.lock:
            now = time.monotonic()
            while self.attempts and self.attempts[0] <= now - 60:
                self.attempts.popleft()
            if len(self.attempts) >= 5:
                raise HTTPException(429, "Too many login attempts", headers={"Retry-After": "60"})
            self.attempts.append(now)


def require_origin(request: Request) -> None:
    if request.headers.get("origin") not in request.app.state.settings.allowed_origins:
        raise HTTPException(403, "Origin rejected")


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except VerificationError:
        return False


def create_session(request: Request) -> tuple[str, str]:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    try:
        with Session(request.app.state.engine) as db:
            from sqlalchemy import delete

            db.execute(delete(AdminSession).where(AdminSession.expires_at <= datetime.now(UTC)))
            db.add(
                AdminSession(
                    token_digest=digest(token),
                    csrf_digest=digest(csrf),
                    expires_at=datetime.now(UTC)
                    + timedelta(minutes=request.app.state.settings.session_minutes),
                )
            )
            db.commit()
    except SQLAlchemyError:
        raise HTTPException(503, "Session store unavailable") from None
    return token, csrf


def require_admin(request: Request) -> str:
    token = request.cookies.get("admin_session", "")
    if not token or len(token) > 128:
        raise HTTPException(401, "Administrator sign-in required")
    try:
        with Session(request.app.state.engine) as db:
            session = db.get(AdminSession, digest(token))
            if session is None:
                raise HTTPException(401, "Session invalid or expired")
            # SQLite test driver returns naive UTC; PostgreSQL returns aware values.
            expires = session.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires <= datetime.now(UTC):
                raise HTTPException(401, "Session invalid or expired")
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                require_origin(request)
                csrf = request.headers.get("x-csrf-token", "")
                if not secrets.compare_digest(digest(csrf), session.csrf_digest):
                    raise HTTPException(403, "CSRF validation failed")
    except SQLAlchemyError:
        raise HTTPException(503, "Session store unavailable") from None
    return digest(token)
