"""
Tests for the email-provider safety validation on Settings.

Verifies the model_validator added for audit item #2:
  - Production must use the real provider (ses), never mock.
  - Selecting ses requires AWS credentials.
  - The safe default (mock) loads cleanly in development.

Settings is constructed with _env_file=None so the real backend/.env does not
leak in; init kwargs take precedence over any ambient environment variables.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

# Minimal required fields so Settings can be built in isolation.
BASE = dict(
    SUPABASE_URL="https://example.supabase.co",
    SUPABASE_SERVICE_ROLE_KEY="service-role-key",
    SUPABASE_JWT_SECRET="jwt-secret",
    VENDOR_JWT_SECRET="vendor-secret",
    _env_file=None,
)


def test_production_rejects_non_ses_provider():
    with pytest.raises(ValidationError):
        Settings(**BASE, APP_ENV="production", EMAIL_PROVIDER="mock")


def test_production_with_ses_and_creds_ok():
    s = Settings(
        **BASE,
        APP_ENV="production",
        EMAIL_PROVIDER="ses",
        AWS_ACCESS_KEY_ID="ak",
        AWS_SECRET_ACCESS_KEY="sk",
    )
    assert s.EMAIL_PROVIDER == "ses"


def test_ses_without_credentials_rejected():
    with pytest.raises(ValidationError):
        Settings(
            **BASE,
            EMAIL_PROVIDER="ses",
            AWS_ACCESS_KEY_ID=None,
            AWS_SECRET_ACCESS_KEY=None,
        )


def test_development_mock_is_the_safe_default(monkeypatch):
    # With nothing set (conftest loads the real .env into the env, so clear it),
    # the provider must fall back to the safe "mock" default and load cleanly.
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    s = Settings(**BASE, APP_ENV="development")
    assert s.EMAIL_PROVIDER == "mock"
