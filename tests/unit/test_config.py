import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def test_safe_defaults():
    settings = Settings(_env_file=None)
    assert settings.trading_mode == "OBSERVATION"
    assert settings.live_enabled is False
    assert "localhost" in settings.allowed_hosts


@pytest.mark.parametrize(
    "change",
    [
        {"trading_mode": "LIVE"},
        {"live_enabled": True},
        {"allowed_hosts": ["*"]},
        {"allowed_origins": ["*"]},
        {"database_url": "sqlite:///unsafe.db"},
        {"app_env": "production"},
        {"admin_password_hash": "plaintext"},
        {"session_minutes": 0},
    ],
)
def test_unsafe_config_rejected(change):
    with pytest.raises((ValidationError, ValueError)):
        Settings(_env_file=None, **change)


def test_production_requires_https_origins(password_hash):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            cookie_secure=True,
            admin_password_hash=password_hash,
        )
    settings = Settings(
        _env_file=None,
        app_env="production",
        cookie_secure=True,
        admin_password_hash=password_hash,
        allowed_origins=["https://trade.example.com"],
    )
    assert settings.cookie_secure


@pytest.mark.parametrize("value", ["false", "FALSE", " false "])
def test_disabled_live_environment_is_accepted(monkeypatch, value):
    monkeypatch.setenv("LIVE_ENABLED", value)
    assert Settings(_env_file=None).live_enabled is False


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on", ""])
def test_live_environment_cannot_enable_execution(monkeypatch, value):
    monkeypatch.setenv("LIVE_ENABLED", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_shipped_environment_example_loads():
    settings = Settings(_env_file=".env.example")
    assert settings.trading_mode == "OBSERVATION"
    assert settings.live_enabled is False
