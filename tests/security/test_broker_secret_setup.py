import stat

import pytest

from scripts.configure_upstox import save_analytics_credential

SYNTHETIC_TOKEN = "synthetic-setup-credential"


def test_local_secret_setup_preserves_other_configuration_and_restricts_permissions(tmp_path):
    environment = tmp_path / ".env"
    environment.write_text("ADMIN_PASSWORD_HASH='untouched'\nUPSTOX_ANALYTICS_TOKEN='old'\n")
    save_analytics_credential(environment, SYNTHETIC_TOKEN, "2027-01-01T00:00:00+05:30")
    assert "ADMIN_PASSWORD_HASH='untouched'" in environment.read_text()
    assert environment.read_text().count("UPSTOX_ANALYTICS_TOKEN=") == 1
    assert stat.S_IMODE(environment.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".algotrade-secret-*"))


def test_invalid_header_input_does_not_modify_environment(tmp_path):
    environment = tmp_path / ".env"
    environment.write_text("UNCHANGED=yes\n")
    with pytest.raises(ValueError):
        save_analytics_credential(environment, "bad\r\ncredential", "2027-01-01T00:00:00Z")
    assert environment.read_text() == "UNCHANGED=yes\n"


def test_symlinked_secret_file_is_rejected(tmp_path):
    target = tmp_path / "existing-secrets"
    target.write_text("UNCHANGED=yes\n")
    environment = tmp_path / ".env"
    environment.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        save_analytics_credential(environment, SYNTHETIC_TOKEN, "2027-01-01T00:00:00Z")
    assert target.read_text() == "UNCHANGED=yes\n"
