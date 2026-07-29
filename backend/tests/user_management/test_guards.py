"""Self-protection (G1) and last-admin (G2) guards on change/delete."""

from tests.user_management.conftest import ADMIN_ID, OTHER_ADMIN_ID, admin_row


def _two_admins() -> list[dict]:
    return [
        admin_row(id=ADMIN_ID, email="admin@bluonx.dev"),
        admin_row(id=OTHER_ADMIN_ID, email="other@bluonx.dev"),
    ]


def _one_admin() -> list[dict]:
    return [admin_row(id=ADMIN_ID, email="admin@bluonx.dev")]


# ── G1 self-protection (a second admin exists, so G2 does not preempt) ────────
class TestSelfProtection:
    def test_cannot_change_own_role(self, admin_client):
        tc = admin_client({"users": _two_admins()})
        resp = tc.patch(f"/api/v1/users/{ADMIN_ID}", json={"role": "project_manager"})
        assert resp.status_code == 409
        assert "change your own role" in resp.json()["detail"].lower()

    def test_cannot_deactivate_self(self, admin_client):
        tc = admin_client({"users": _two_admins()})
        resp = tc.patch(f"/api/v1/users/{ADMIN_ID}", json={"is_active": False})
        assert resp.status_code == 409
        assert "deactivate your own account" in resp.json()["detail"].lower()

    def test_cannot_delete_self(self, admin_client):
        tc = admin_client({"users": _two_admins()})
        resp = tc.delete(f"/api/v1/users/{ADMIN_ID}")
        assert resp.status_code == 409
        assert "delete your own account" in resp.json()["detail"].lower()


# ── G2 last-admin (the actor is the sole active admin) ────────────────────────
class TestLastAdmin:
    def test_cannot_demote_last_admin(self, admin_client):
        tc = admin_client({"users": _one_admin()})
        resp = tc.patch(f"/api/v1/users/{ADMIN_ID}", json={"role": "project_manager"})
        assert resp.status_code == 409
        assert "last active admin" in resp.json()["detail"].lower()

    def test_cannot_deactivate_last_admin(self, admin_client):
        tc = admin_client({"users": _one_admin()})
        resp = tc.patch(f"/api/v1/users/{ADMIN_ID}", json={"is_active": False})
        assert resp.status_code == 409
        assert "last active admin" in resp.json()["detail"].lower()

    def test_cannot_delete_last_admin(self, admin_client):
        tc = admin_client({"users": _one_admin()})
        resp = tc.delete(f"/api/v1/users/{ADMIN_ID}")
        assert resp.status_code == 409
        assert "last active admin" in resp.json()["detail"].lower()


# ── G1 + G2 together ──────────────────────────────────────────────────────────
class TestGuardsComposite:
    def test_can_deactivate_the_other_admin(self, admin_client):
        """With two admins, deactivating the OTHER one is allowed (leaves one)."""
        tc = admin_client(
            {
                "users": _two_admins(),
                "confirmed": {ADMIN_ID: "2026-06-01T00:00:00+00:00",
                              OTHER_ADMIN_ID: "2026-06-01T00:00:00+00:00"},
            }
        )
        resp = tc.patch(
            f"/api/v1/users/{OTHER_ADMIN_ID}", json={"is_active": False}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_active"] is False
        assert body["status"] == "deactivated"

    def test_last_admin_still_blocked(self, admin_client):
        """Once only one admin remains, deactivating them is blocked."""
        tc = admin_client({"users": _one_admin()})
        resp = tc.patch(f"/api/v1/users/{ADMIN_ID}", json={"is_active": False})
        assert resp.status_code == 409
        assert "last active admin" in resp.json()["detail"].lower()

    def test_distinct_409_messages(self, admin_client):
        """G1 and G2 return different details for the same self-deactivate call,
        depending on whether another admin exists."""
        g1 = admin_client({"users": _two_admins()}).patch(
            f"/api/v1/users/{ADMIN_ID}", json={"is_active": False}
        )
        g2 = admin_client({"users": _one_admin()}).patch(
            f"/api/v1/users/{ADMIN_ID}", json={"is_active": False}
        )
        assert g1.status_code == g2.status_code == 409
        assert g1.json()["detail"] != g2.json()["detail"]
