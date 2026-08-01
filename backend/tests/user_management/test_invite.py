"""Invite flow: metadata + redirect, role validation, duplicates, partial failure."""

import logging
from types import SimpleNamespace
from uuid import uuid4

from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError

from tests.user_management.conftest import ADMIN_ID, user_row


def _invite_ok(new_id: str):
    return SimpleNamespace(user=SimpleNamespace(id=new_id, confirmed_at=None))


class TestInviteHappyPath:
    def test_invite_calls_supabase_with_metadata_and_redirect(self, admin_client):
        new_id = str(uuid4())
        tc = admin_client(
            {
                "invite_result": _invite_ok(new_id),
                "users": [
                    user_row(
                        id=new_id,
                        email="new@bluonx.dev",
                        full_name="New Person",
                        role="project_manager",
                    )
                ],
            }
        )
        resp = tc.post(
            "/api/v1/users/invite",
            json={
                "email": "new@bluonx.dev",
                "full_name": "New Person",
                "role": "project_manager",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "new@bluonx.dev"
        assert body["status"] == "pending"
        # invited_by was stamped by the follow-up write.
        assert body["invited_by"] == ADMIN_ID

        invite = tc.db.auth.admin.invite_user_by_email
        invite.assert_called_once()
        args, _ = invite.call_args
        assert args[0] == "new@bluonx.dev"
        options = args[1]
        assert options["data"] == {"full_name": "New Person", "role": "project_manager"}
        assert options["redirect_to"].endswith("/accept-invite")


class TestInviteValidation:
    def test_invalid_role_is_422_and_never_reaches_supabase(self, admin_client):
        tc = admin_client({"users": []})
        resp = tc.post(
            "/api/v1/users/invite",
            json={"email": "x@bluonx.dev", "full_name": "X", "role": "superadmin"},
        )
        assert resp.status_code == 422
        tc.db.auth.admin.invite_user_by_email.assert_not_called()

    def test_invalid_email_is_422(self, admin_client):
        tc = admin_client({"users": []})
        resp = tc.post(
            "/api/v1/users/invite",
            json={"email": "not-an-email", "full_name": "X", "role": "admin"},
        )
        assert resp.status_code == 422
        tc.db.auth.admin.invite_user_by_email.assert_not_called()


class TestInviteDuplicate:
    def test_already_registered_auth_error_is_409(self, admin_client):
        err = AuthApiError(
            "A user with this email address has already been registered", 422, "email_exists"
        )
        tc = admin_client({"invite_result": err, "users": []})
        resp = tc.post(
            "/api/v1/users/invite",
            json={"email": "dupe@bluonx.dev", "full_name": "Dupe", "role": "admin"},
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"].lower()

    def test_unique_violation_23505_backstop_is_409(self, admin_client):
        err = APIError(
            {"code": "23505", "message": "duplicate key value violates unique constraint"}
        )
        tc = admin_client({"invite_result": err, "users": []})
        resp = tc.post(
            "/api/v1/users/invite",
            json={"email": "dupe2@bluonx.dev", "full_name": "Dupe2", "role": "admin"},
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"].lower()


class TestInvitePartialFailure:
    def test_invited_by_write_failure_still_returns_201_and_logs(
        self, admin_client, caplog
    ):
        new_id = str(uuid4())
        tc = admin_client(
            {
                "invite_result": _invite_ok(new_id),
                "users": [
                    user_row(id=new_id, email="p@bluonx.dev", full_name="P", role="admin")
                ],
                "raise_on": {"users": {"update": APIError({"message": "boom"})}},
            }
        )
        with caplog.at_level(logging.ERROR, logger="app.services.user_service"):
            resp = tc.post(
                "/api/v1/users/invite",
                json={"email": "p@bluonx.dev", "full_name": "P", "role": "admin"},
            )
        assert resp.status_code == 201
        # The invite itself is real; only attribution failed, and it was logged.
        assert resp.json()["invited_by"] is None
        assert any("invited_by" in rec.message for rec in caplog.records)
