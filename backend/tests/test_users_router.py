"""Tests for the users router — /api/v1/users."""


class TestGetCurrentUser:
    """Tests for GET /api/v1/users/me."""

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

    def test_returns_correct_admin_data(self, client, auth_headers):
        """Should return correct data for admin@bluonx.dev."""
        resp = client.get("/api/v1/users/me", headers=auth_headers)
        data = resp.json()
        assert data["email"] == "admin@bluonx.dev"
        assert data["role"] == "admin"
        assert data["is_active"] is True

    def test_unauthenticated_returns_403(self, client):
        """Should return 403 when no auth header is provided."""
        resp = client.get("/api/v1/users/me")
        assert resp.status_code == 403


class TestListUsers:
    """Tests for GET /api/v1/users (admin-only stub)."""

    def test_admin_gets_empty_list_stub(self, client, auth_headers):
        """Admin should get an empty list (stub implementation)."""
        resp = client.get("/api/v1/users", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_unauthenticated_returns_403(self, client):
        """Should return 403 without auth."""
        resp = client.get("/api/v1/users")
        assert resp.status_code == 403


class TestUserCRUDStubs:
    """Tests for stub endpoints — should return 501."""

    def test_get_user_by_id_returns_501(self, client, auth_headers):
        """GET /users/{id} should return 501 (not implemented)."""
        resp = client.get(
            "/api/v1/users/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 501

    def test_update_user_returns_501(self, client, auth_headers):
        """PATCH /users/{id} should return 501 (not implemented)."""
        resp = client.patch(
            "/api/v1/users/00000000-0000-0000-0000-000000000000",
            json={"full_name": "Test"},
            headers=auth_headers,
        )
        assert resp.status_code == 501

    def test_delete_user_returns_501(self, client, auth_headers):
        """DELETE /users/{id} should return 501 (not implemented)."""
        resp = client.delete(
            "/api/v1/users/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 501
