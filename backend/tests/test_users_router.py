"""Tests for the users router — /api/v1/users.

The live-endpoint tests here assert shape and status codes only. They must not
pin a specific seeded identity (e.g. a hard-coded admin email), or they stop
passing on any database but the one they were written against.
"""

import pytest


class TestGetCurrentUser:
    """Tests for GET /api/v1/users/me."""

    @pytest.mark.requires_db
    def test_returns_authenticated_user_profile(self, client, auth_headers):
        """Should return the authenticated user's full profile."""
        resp = client.get("/api/v1/users/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        # Required fields present
        assert "id" in data
        assert "email" in data
        assert "full_name" in data
        assert "role" in data
        assert "is_active" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_unauthenticated_returns_403(self, client):
        """Should return 403 when no auth header is provided."""
        resp = client.get("/api/v1/users/me")
        assert resp.status_code == 403


class TestListUsers:
    """Tests for GET /api/v1/users (admin-only)."""

    @pytest.mark.requires_db
    def test_admin_gets_a_list_with_status(self, client, auth_headers):
        """Admin should get a list of users, each carrying a derived status.
        Isolated behavior (merge/status derivation) is covered under
        tests/user_management; here we just confirm the live endpoint answers."""
        resp = client.get("/api/v1/users", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # The caller is signed in, so they are in the list at minimum. Which
        # rows come back depends on the database, so assert the shape rather
        # than any particular user.
        assert data
        for user in data:
            assert user["status"] in ("active", "pending", "deactivated")

    def test_unauthenticated_returns_403(self, client):
        """Should return 403 without auth."""
        resp = client.get("/api/v1/users")
        assert resp.status_code == 403


@pytest.mark.requires_db
class TestUserCRUDStubs:
    """GET /users/{id} remains an out-of-scope 501 stub; PATCH/DELETE are now
    implemented (behavior covered in tests/user_management)."""

    def test_get_user_by_id_returns_501(self, client, auth_headers):
        """GET /users/{id} should return 501 (single-user read is out of scope)."""
        resp = client.get(
            "/api/v1/users/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 501

    def test_update_missing_user_returns_404(self, client, auth_headers):
        """PATCH on a nonexistent user should 404 (no longer a 501 stub)."""
        resp = client.patch(
            "/api/v1/users/00000000-0000-0000-0000-000000000000",
            json={"full_name": "Test"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_delete_missing_user_returns_404(self, client, auth_headers):
        """DELETE on a nonexistent user should 404 (no longer a 501 stub)."""
        resp = client.delete(
            "/api/v1/users/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404
