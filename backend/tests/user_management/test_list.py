"""GET /users merges public.users with auth and derives per-account status."""

from uuid import uuid4

from tests.user_management.conftest import ADMIN_ID, admin_row, user_row


def test_status_derivation_and_soft_deleted_included(admin_client):
    u_active = str(uuid4())
    u_pending = str(uuid4())
    u_deact = str(uuid4())
    u_deleted = str(uuid4())

    spec = {
        "users": [
            admin_row(id=ADMIN_ID, email="admin@bluonx.dev"),
            user_row(id=u_active, email="active@bluonx.dev"),
            user_row(id=u_pending, email="pending@bluonx.dev"),
            user_row(id=u_deact, email="deact@bluonx.dev", is_active=False),
            user_row(
                id=u_deleted,
                email="deleted@bluonx.dev",
                deleted_at="2026-07-05T00:00:00+00:00",
            ),
        ],
        "confirmed": {
            ADMIN_ID: "2026-06-01T00:00:00+00:00",
            u_active: "2026-06-02T00:00:00+00:00",
            u_deact: "2026-06-03T00:00:00+00:00",
            u_deleted: "2026-06-04T00:00:00+00:00",
            # u_pending intentionally absent -> no confirmed_at -> pending
        },
    }
    tc = admin_client(spec)
    resp = tc.get("/api/v1/users")
    assert resp.status_code == 200

    by_email = {row["email"]: row for row in resp.json()}
    # Soft-deleted user is still returned so the admin can see it.
    assert len(by_email) == 5
    assert by_email["admin@bluonx.dev"]["status"] == "active"
    assert by_email["active@bluonx.dev"]["status"] == "active"
    assert by_email["pending@bluonx.dev"]["status"] == "pending"
    assert by_email["deact@bluonx.dev"]["status"] == "deactivated"
    assert by_email["deleted@bluonx.dev"]["status"] == "deactivated"


def test_empty_list(admin_client):
    tc = admin_client({"users": []})
    resp = tc.get("/api/v1/users")
    assert resp.status_code == 200
    assert resp.json() == []
