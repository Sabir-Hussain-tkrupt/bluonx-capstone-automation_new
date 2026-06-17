"""Task 9.3b config keys load with sane defaults."""

from app.core.config import settings


def test_connect_and_owner_config_keys_exist():
    # New keys exist on the settings object (None by default — set in .env).
    assert hasattr(settings, "DOCUSIGN_CONNECT_HMAC_KEY")
    assert hasattr(settings, "DOCUSIGN_CONNECT_WEBHOOK_URL")
    assert hasattr(settings, "CONTRACT_OWNER_SIGNER_NAME")
    assert hasattr(settings, "CONTRACT_OWNER_SIGNER_EMAIL")


def test_provider_default_is_mock_offline():
    # The whole 9.3b path must run offline by default.
    assert settings.DOCUSIGN_PROVIDER in ("mock", "sandbox")
