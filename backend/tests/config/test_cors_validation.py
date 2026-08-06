"""Production CORS guard (Task 2.6 hardening).

CORS_ORIGINS had no production validator, unlike EMAIL_PROVIDER and
FRONTEND_BASE_URL. A deploy that forgot it booted cleanly and then failed every
browser call with an opaque CORS error. These tests pin the refusal.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

# Minimal required fields, with _env_file=None so the real backend/.env cannot
# leak in and flip a default-value assertion. Mirrors
# tests/email/test_settings_email_provider.py.
BASE = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
    "SUPABASE_JWT_SECRET": "jwt-secret",
    "VENDOR_JWT_SECRET": "vendor-secret",
    "_env_file": None,
}


@pytest.fixture(autouse=True)
def _clear_ambient_log_vars(monkeypatch):
    """conftest load_dotenv()s backend/.env into os.environ, which pydantic reads
    even with _env_file=None. Clear the logging vars so the derived-default tests
    assert on the code's behaviour, not on a developer's local .env."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)


def _dev_settings(**overrides) -> Settings:
    return Settings(**BASE, **{"APP_ENV": "development", **overrides})


def _prod_settings(**overrides) -> Settings:
    """Build a production Settings, satisfying the OTHER production validators.

    APP_ENV=production also trips _validate_email_provider and
    _validate_frontend_base_url, so those have to be given valid values or every
    test here would fail for the wrong reason.
    """
    base = {
        "APP_ENV": "production",
        "EMAIL_PROVIDER": "ses",
        "AWS_ACCESS_KEY_ID": "test-access-key",
        "AWS_SECRET_ACCESS_KEY": "test-secret-key",
        "FRONTEND_BASE_URL": "https://app.bluonx.com",
        "CORS_ORIGINS": ["https://app.bluonx.com"],
    }
    base.update(overrides)
    return Settings(**BASE, **base)


class TestProductionRejectsUnsafeOrigins:
    @pytest.mark.parametrize(
        "origins",
        [
            pytest.param(["http://localhost:5173"], id="localhost"),
            pytest.param(["http://127.0.0.1:5173"], id="loopback-ip"),
            pytest.param(["https://app.bluonx.com", "http://localhost:5173"], id="mixed"),
        ],
    )
    def test_localhost_origin_refuses_to_start(self, origins):
        with pytest.raises(ValidationError, match="localhost"):
            _prod_settings(CORS_ORIGINS=origins)

    def test_wildcard_refuses_to_start(self):
        with pytest.raises(ValidationError, match=r"must not contain"):
            _prod_settings(CORS_ORIGINS=["*"])

    def test_empty_list_refuses_to_start(self):
        with pytest.raises(ValidationError, match="at least one origin"):
            _prod_settings(CORS_ORIGINS=[])

    def test_plain_http_origin_refuses_to_start(self):
        # Not localhost, but still unencrypted.
        with pytest.raises(ValidationError, match="https"):
            _prod_settings(CORS_ORIGINS=["http://app.bluonx.com"])


class TestProductionAcceptsRealOrigins:
    def test_single_https_origin(self):
        s = _prod_settings(CORS_ORIGINS=["https://app.bluonx.com"])
        assert s.CORS_ORIGINS == ["https://app.bluonx.com"]

    def test_multiple_https_origins(self):
        # Staff app and a separately-hosted vendor portal.
        origins = ["https://app.bluonx.com", "https://bids.bluonx.com"]
        assert _prod_settings(CORS_ORIGINS=origins).CORS_ORIGINS == origins


class TestNonProductionIsUnaffected:
    @pytest.mark.parametrize("env", ["development", "staging", "test"])
    def test_localhost_still_allowed(self, env):
        s = _dev_settings(APP_ENV=env, CORS_ORIGINS=["http://localhost:5173"])
        assert s.CORS_ORIGINS == ["http://localhost:5173"]

    def test_wildcard_still_allowed_in_dev(self):
        assert _dev_settings(CORS_ORIGINS=["*"]).CORS_ORIGINS == ["*"]


class TestLoggingSettings:
    def test_log_format_defaults_to_console_outside_production(self):
        assert _dev_settings().LOG_FORMAT == "console"

    def test_log_format_defaults_to_json_in_production(self):
        # Derived from APP_ENV so a production deploy gets structured logs
        # without a separate env var to forget.
        assert _prod_settings().LOG_FORMAT == "json"

    def test_explicit_log_format_wins_over_the_derived_default(self):
        assert _prod_settings(LOG_FORMAT="console").LOG_FORMAT == "console"

    def test_log_level_defaults_to_info(self):
        assert _dev_settings().LOG_LEVEL == "INFO"

    def test_log_level_is_normalised_to_upper_case(self):
        assert _dev_settings(LOG_LEVEL="debug").LOG_LEVEL == "DEBUG"

    def test_invalid_log_format_refuses_to_start(self):
        with pytest.raises(ValidationError, match="LOG_FORMAT"):
            _dev_settings(LOG_FORMAT="xml")

    def test_invalid_log_level_refuses_to_start(self):
        with pytest.raises(ValidationError, match="LOG_LEVEL"):
            _dev_settings(LOG_LEVEL="verbose")
