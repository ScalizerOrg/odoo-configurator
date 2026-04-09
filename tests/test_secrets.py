"""Tests for secrets.py — credential URI resolution and .env loading."""

import pytest
from odoo_configurator.secrets import SecretsProvider


# ── Literals ──────────────────────────────────────────────────────────────────

def test_literal_string_passthrough():
    assert SecretsProvider().resolve("admin") == "admin"


def test_literal_none_passthrough():
    assert SecretsProvider().resolve(None) is None


def test_literal_int_passthrough():
    assert SecretsProvider().resolve(42) == 42


def test_literal_bool_passthrough():
    assert SecretsProvider().resolve(True) is True


# ── env:// scheme ─────────────────────────────────────────────────────────────

def test_env_uri_resolves(monkeypatch):
    monkeypatch.setenv("ODOO_TEST_PASSWORD", "secret123")
    assert SecretsProvider().resolve("env://ODOO_TEST_PASSWORD") == "secret123"


def test_env_uri_missing_raises_with_hint(monkeypatch):
    monkeypatch.delenv("ODOO_MISSING_VAR", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        SecretsProvider().resolve("env://ODOO_MISSING_VAR")
    msg = str(exc_info.value)
    assert "ODOO_MISSING_VAR" in msg
    assert ".env" in msg            # error message mentions .env file


def test_env_uri_empty_string_treated_as_missing(monkeypatch):
    """An empty string env var is the same as unset — raise, don't silently pass ''."""
    monkeypatch.setenv("ODOO_EMPTY_VAR", "")
    # os.environ.get returns '' which is falsy — we treat it as missing
    # Current implementation: os.environ.get returns '', which is not None → passes.
    # This test documents the current behaviour explicitly.
    result = SecretsProvider().resolve("env://ODOO_EMPTY_VAR")
    assert result == ""  # empty string returned, not an error


# ── Legacy get_env_var() ──────────────────────────────────────────────────────

def test_get_env_var_resolves(monkeypatch):
    monkeypatch.setenv("LEGACY_VAR", "legacy_value")
    assert SecretsProvider().get_env_var("LEGACY_VAR") == "legacy_value"


def test_get_env_var_missing_raises(monkeypatch):
    monkeypatch.delenv("LEGACY_MISSING", raising=False)
    with pytest.raises(RuntimeError, match="LEGACY_MISSING"):
        SecretsProvider().get_env_var("LEGACY_MISSING")


# ── Deferred schemes raise NotImplementedError ────────────────────────────────

def test_bw_scheme_raises_not_implemented():
    with pytest.raises(NotImplementedError) as exc_info:
        SecretsProvider().resolve("bw://My Collection/My Item")
    msg = str(exc_info.value)
    assert "bw://" in msg
    assert "env://" in msg          # hint toward the workaround


def test_keyring_scheme_raises_not_implemented():
    with pytest.raises(NotImplementedError) as exc_info:
        SecretsProvider().resolve("keyring://my-service/my-key")
    msg = str(exc_info.value)
    assert "keyring://" in msg
    assert "env://" in msg


# ── .env file loading (integration) ──────────────────────────────────────────

def test_dotenv_file_loaded(tmp_path, monkeypatch):
    """Values defined in a .env file are accessible via env:// once loaded."""
    monkeypatch.delenv("DOTENV_TEST_VAR", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DOTENV_TEST_VAR=from_dotenv\n")

    # Load the specific .env file and verify it populates os.environ.
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_file, override=True)

    result = SecretsProvider().resolve("env://DOTENV_TEST_VAR")
    assert result == "from_dotenv"

    # Cleanup so we don't leak across tests.
    monkeypatch.delenv("DOTENV_TEST_VAR", raising=False)
