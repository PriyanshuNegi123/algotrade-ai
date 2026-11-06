import re
from typing import Literal

from pydantic import AwareDatetime, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "production"] = "development"
    trading_mode: Literal["OBSERVATION", "PAPER"] = "OBSERVATION"
    live_enabled: Literal[False] = False
    database_url: SecretStr = SecretStr("postgresql+psycopg://algotrade@localhost:5432/algotrade")
    admin_password_hash: SecretStr = SecretStr("")
    cookie_secure: bool = False
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    allowed_origins: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]
    session_minutes: int = Field(default=15, ge=1, le=30)
    upstox_analytics_token: SecretStr = SecretStr("")
    upstox_analytics_expires_at: AwareDatetime | None = None

    @field_validator("upstox_analytics_token")
    @classmethod
    def validate_bearer_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if token and (len(token) > 8192 or re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token) is None):
            raise ValueError("Invalid Analytics credential format")
        return value

    @field_validator("live_enabled", mode="before")
    @classmethod
    def parse_disabled_live_flag(cls, value: object) -> object:
        # Environment values are strings. Keep the literal-false permission boundary.
        if isinstance(value, str) and value.strip().lower() == "false":
            return False
        return value

    @model_validator(mode="after")
    def validate_safety(self) -> "Settings":
        if bool(self.upstox_analytics_token.get_secret_value()) != bool(
            self.upstox_analytics_expires_at
        ):
            raise ValueError("Analytics credential and timezone-aware expiry must be set together")
        url = make_url(self.database_url.get_secret_value())
        if url.drivername != "postgresql+psycopg" and not (
            self.app_env == "test" and url.drivername == "sqlite"
        ):
            raise ValueError("PostgreSQL with psycopg is required outside tests")
        password_hash = self.admin_password_hash.get_secret_value()
        if password_hash:
            from argon2 import extract_parameters

            extract_parameters(password_hash)
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ValueError("Explicit allowed hosts required")
        if not self.allowed_origins or any("*" in origin for origin in self.allowed_origins):
            raise ValueError("Explicit allowed origins required")
        if self.app_env == "production":
            if not self.cookie_secure or not password_hash:
                raise ValueError("Production requires secure cookies and an administrator hash")
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise ValueError("Production origins must use HTTPS")
        return self
