"""Consent-URL construction + consent_required handling (Task 9.3a).

On the first JWT mint the impersonated user must grant consent once. The SDK
raises `consent_required`; the client catches it and surfaces the one-time
consent URL so the grant is self-service.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from docusign_esign import ApiException

from app.core.config import settings
from app.services.docusign_client import (
    DocuSignConsentRequired,
    SandboxDocuSignAuthProvider,
    build_consent_url,
)


class TestBuildConsentUrl:
    def test_exact_shape(self):
        url = build_consent_url(
            oauth_base="account-d.docusign.com",
            integration_key="abc-123",
            redirect_uri="http://localhost:8000/cb",
            scopes="signature impersonation",
        )
        assert url.startswith("https://account-d.docusign.com/oauth/auth?")
        parsed = urlparse(url)
        assert parsed.netloc == "account-d.docusign.com"
        assert parsed.path == "/oauth/auth"
        qs = parse_qs(parsed.query)
        assert qs["response_type"] == ["code"]
        assert qs["scope"] == ["signature impersonation"]
        assert qs["client_id"] == ["abc-123"]
        assert qs["redirect_uri"] == ["http://localhost:8000/cb"]

    def test_scope_is_url_encoded(self):
        # The space between scopes must be percent-encoded in the raw string.
        url = build_consent_url(
            oauth_base="account-d.docusign.com",
            integration_key="k",
            redirect_uri="http://localhost/cb",
            scopes="signature impersonation",
        )
        assert "scope=signature%20impersonation" in url


class TestConsentRequiredPath:
    def test_consent_required_raises_with_url(self, monkeypatch, tmp_path):
        # Real key never used — the SDK call is mocked to raise consent_required.
        key = tmp_path / "key.pem"
        key.write_bytes(b"dummy-key-bytes")
        monkeypatch.setattr(settings, "DOCUSIGN_INTEGRATION_KEY", "ik-xyz")
        monkeypatch.setattr(settings, "DOCUSIGN_USER_ID", "user-1")
        monkeypatch.setattr(settings, "DOCUSIGN_PRIVATE_KEY_PATH", str(key))
        monkeypatch.setattr(settings, "DOCUSIGN_OAUTH_BASE_URL", "account-d.docusign.com")
        monkeypatch.setattr(settings, "DOCUSIGN_REDIRECT_URI", "http://localhost:8000/cb")
        monkeypatch.setattr(settings, "DOCUSIGN_JWT_SCOPES", "signature impersonation")

        # The SDK reads .body off the exception; set it to the consent error.
        def _raise_consent_with_body(*_a, **_k):
            exc = ApiException(status=400, reason="Bad Request")
            exc.body = b'{"error":"consent_required"}'
            raise exc

        monkeypatch.setattr(
            "docusign_esign.ApiClient.request_jwt_user_token",
            _raise_consent_with_body,
            raising=True,
        )

        provider = SandboxDocuSignAuthProvider()
        with pytest.raises(DocuSignConsentRequired) as excinfo:
            provider.mint()

        expected = build_consent_url(
            oauth_base="account-d.docusign.com",
            integration_key="ik-xyz",
            redirect_uri="http://localhost:8000/cb",
            scopes="signature impersonation",
        )
        assert excinfo.value.consent_url == expected

    def test_non_consent_api_error_propagates(self, monkeypatch, tmp_path):
        key = tmp_path / "key.pem"
        key.write_bytes(b"dummy-key-bytes")
        monkeypatch.setattr(settings, "DOCUSIGN_INTEGRATION_KEY", "ik")
        monkeypatch.setattr(settings, "DOCUSIGN_USER_ID", "user-1")
        monkeypatch.setattr(settings, "DOCUSIGN_PRIVATE_KEY_PATH", str(key))

        def _raise_other(*_a, **_k):
            exc = ApiException(status=401, reason="Unauthorized")
            exc.body = b'{"error":"invalid_grant"}'
            raise exc

        monkeypatch.setattr(
            "docusign_esign.ApiClient.request_jwt_user_token", _raise_other, raising=True
        )

        provider = SandboxDocuSignAuthProvider()
        with pytest.raises(ApiException):
            provider.mint()
