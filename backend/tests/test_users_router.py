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
    """Tests for GET /api/v1/users (admin-only)."""

    def test_admin_gets_a_list_with_status(self, client, auth_headers):
        """Admin should get a list of users, each carrying a derived status.
        Isolated behavior (merge/status derivation) is covered under
        tests/user_management; here we just confirm the live endpoint answers."""
        resp = client.get("/api/v1/users", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # The signed-in admin must appear, with a status field.
        me = next((u for u in data if u["email"] == "admin@bluonx.dev"), None)
        assert me is not None
        assert me["status"] in ("active", "pending", "deactivated")

    def test_unauthenticated_returns_403(self, client):
        """Should return 403 without auth."""
        resp = client.get("/api/v1/users")
        assert resp.status_code == 403


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
