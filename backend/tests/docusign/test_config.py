"""Config loading for the DocuSign keys (Task 9.3a).

Asserts the new keys exist, the defaults are correct, and the OAuth host is
kept distinct from the REST base.
"""

from __future__ import annotations

from app.core.config import Settings, settings


def _default(name: str):
    return Settings.model_fields[name].default


class TestDocuSignDefaults:
    def test_provider_defaults_to_mock(self):
        # Mock is the safe default — runs without creds/consent.
        assert _default("DOCUSIGN_PROVIDER") == "mock"

    def test_oauth_base_defaults_to_sandbox_host(self):
        assert _default("DOCUSIGN_OAUTH_BASE_URL") == "account-d.docusign.com"

    def test_jwt_scopes_default(self):
        assert _default("DOCUSIGN_JWT_SCOPES") == "signature impersonation"

    def test_token_expires_in_default(self):
        assert _default("DOCUSIGN_TOKEN_EXPIRES_IN") == 3600


class TestDocuSignKeysPresent:
    def test_all_keys_declared(self):
        for key in (
            "DOCUSIGN_PROVIDER",
            "DOCUSIGN_ACCOUNT_ID",
            "DOCUSIGN_USER_ID",
            "DOCUSIGN_INTEGRATION_KEY",
            "DOCUSIGN_PRIVATE_KEY_PATH",
            "DOCUSIGN_ACCOUNT_BASE_URL",
            "DOCUSIGN_OAUTH_BASE_URL",
            "DOCUSIGN_JWT_SCOPES",
            "DOCUSIGN_REDIRECT_URI",
            "DOCUSIGN_TOKEN_EXPIRES_IN",
        ):
            assert hasattr(settings, key), f"missing config key {key}"

    def test_oauth_host_distinct_from_rest_base(self):
        # OAuth host (token mint/consent) must not be the REST API base.
        # The OAuth default has no scheme and is the dedicated auth host.
        assert "://" not in settings.DOCUSIGN_OAUTH_BASE_URL
        if settings.DOCUSIGN_ACCOUNT_BASE_URL:
            assert settings.DOCUSIGN_OAUTH_BASE_URL not in settings.DOCUSIGN_ACCOUNT_BASE_URL
