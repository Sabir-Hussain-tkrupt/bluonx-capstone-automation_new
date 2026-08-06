"""Tests for JWT authentication and authorization."""

import jwt as pyjwt
import pytest


class TestJWTDecoding:
    """Unit tests for the _decode_token function."""

    def test_malformed_token_rejected(self, client):
        """A completely garbage token should return 401."""
        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert resp.status_code == 401

    def test_expired_token_rejected(self, client):
        """An expired JWT should return 401 with 'expired' message."""
        from app.core.config import settings

        # Craft an expired token
        expired_payload = {
            "sub": "00000000-0000-0000-0000-000000000000",
            "email": "test@test.com",
            "aud": "authenticated",
            "exp": 1000000000,  # Far in the past
            "iat": 999999000,
        }
        token = pyjwt.encode(expired_payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

    def test_unsupported_algorithm_rejected(self, client):
        """A token with an unsupported algorithm (RS256) should return 401."""
        # Craft a token with RS256 header but HS256 body (will be rejected)
        import json
        import base64

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "test", "aud": "authenticated"}).encode()
        ).rstrip(b"=").decode()
        fake_token = f"{header}.{payload}.fakesignature"

        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {fake_token}"},
        )
        assert resp.status_code == 401

    def test_none_algorithm_rejected(self, client):
        """A token with alg=none should be rejected."""
        import json
        import base64

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "test", "aud": "authenticated"}).encode()
        ).rstrip(b"=").decode()
        fake_token = f"{header}.{payload}."

        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {fake_token}"},
        )
        assert resp.status_code == 401

    def test_missing_auth_header_returns_403(self, client):
        """No Authorization header should return 403 (HTTPBearer default)."""
        resp = client.get("/api/v1/users/me")
        assert resp.status_code == 403

    def test_wrong_audience_rejected(self, client):
        """A token with wrong audience should be rejected."""
        from app.core.config import settings

        bad_payload = {
            "sub": "00000000-0000-0000-0000-000000000000",
            "email": "test@test.com",
            "aud": "wrong-audience",
            "exp": 9999999999,
            "iat": 1000000000,
        }
        token = pyjwt.encode(bad_payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


@pytest.mark.requires_db
class TestAuthenticatedAccess:
    """Integration tests using a real JWT from Supabase Auth."""

    def test_valid_token_accepted(self, client, auth_headers):
        """A valid admin JWT should be accepted by protected endpoints."""
        resp = client.get("/api/v1/users/me", headers=auth_headers)
        assert resp.status_code == 200
