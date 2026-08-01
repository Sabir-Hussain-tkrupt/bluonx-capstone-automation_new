"""Resend-invite: re-send for unconfirmed users, 409 once confirmed, 404 if gone."""

from uuid import uuid4

from tests.user_management.conftest import user_row


def test_resend_for_unconfirmed_user(admin_client):
    uid = str(uuid4())
    tc = admin_client(
        {
            "users": [user_row(id=uid, email="pending@bluonx.dev")],
            "confirmed": {},  # not confirmed
        }
    )
    resp = tc.post(f"/api/v1/users/{uid}/resend-invite")
    assert resp.status_code == 200
    assert "resent" in resp.json()["detail"].lower()
    tc.db.auth.admin.invite_user_by_email.assert_called_once()


def test_resend_conflicts_when_already_confirmed(admin_client):
    uid = str(uuid4())
    tc = admin_client(
        {
            "users": [user_row(id=uid, email="done@bluonx.dev")],
            "confirmed": {uid: "2026-06-01T00:00:00+00:00"},
        }
    )
    resp = tc.post(f"/api/v1/users/{uid}/resend-invite")
    assert resp.status_code == 409
    assert "already accepted" in resp.json()["detail"].lower()
    tc.db.auth.admin.invite_user_by_email.assert_not_called()


def test_resend_404_for_unknown_user(admin_client):
    tc = admin_client({"users": []})
    resp = tc.post(f"/api/v1/users/{uuid4()}/resend-invite")
    assert resp.status_code == 404
