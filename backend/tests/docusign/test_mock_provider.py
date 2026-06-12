"""Mock DocuSign auth provider (Task 9.3a).

The mock returns a synthetic token with no network call so unit tests and
local dev run without consent or creds — same role EMAIL_PROVIDER=mock plays.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.docusign_client import (
    DocuSignAuthProvider,
    MintedToken,
    MockDocuSignAuthProvider,
    SandboxDocuSignAuthProvider,
    create_docusign_provider,
)


class TestMockProvider:
    def test_implements_protocol(self):
        assert isinstance(MockDocuSignAuthProvider(), DocuSignAuthProvider)

    def test_mint_returns_minted_token(self):
        result = MockDocuSignAuthProvider().mint()
        assert isinstance(result, MintedToken)

    def test_mint_returns_synthetic_token(self):
        result = MockDocuSignAuthProvider().mint()
        assert result.access_token.startswith("mock-")
        assert result.access_token != MockDocuSignAuthProvider().mint().access_token

    def test_expires_in_matches_config(self):
        result = MockDocuSignAuthProvider().mint()
        assert result.expires_in == settings.DOCUSIGN_TOKEN_EXPIRES_IN


class TestProviderFactory:
    def test_factory_returns_mock_by_default(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUSIGN_PROVIDER", "mock")
        assert isinstance(create_docusign_provider(), MockDocuSignAuthProvider)

    def test_factory_returns_mock_for_unknown_value(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUSIGN_PROVIDER", "something-else")
        assert isinstance(create_docusign_provider(), MockDocuSignAuthProvider)

    def test_factory_returns_sandbox_when_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUSIGN_PROVIDER", "sandbox")
        monkeypatch.setattr(settings, "DOCUSIGN_INTEGRATION_KEY", "ik")
        monkeypatch.setattr(settings, "DOCUSIGN_USER_ID", "uid")
        monkeypatch.setattr(settings, "DOCUSIGN_PRIVATE_KEY_PATH", "secrets/x.pem")
        assert isinstance(create_docusign_provider(), SandboxDocuSignAuthProvider)

    def test_sandbox_factory_requires_creds(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUSIGN_PROVIDER", "sandbox")
        monkeypatch.setattr(settings, "DOCUSIGN_INTEGRATION_KEY", None)
        with pytest.raises(RuntimeError):
            create_docusign_provider()
