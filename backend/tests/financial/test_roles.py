"""Task 2.0 — financial roles: auth helpers, invite metadata, role assignment."""

import asyncio

import pytest
from fastapi import HTTPException

from app.core import auth
from app.services import user_service
from tests.financial._memdb import MemDB, api_error
from tests.financial.conftest import ADMIN, ADMIN_ID, FINANCE, PM, identity


# ── user_has_any_role / require_roles ────────────────────────────────────────
class TestRoleChecks:
    def test_admin_passes_every_check(self):
        assert auth.user_has_any_role(ADMIN, "finance")

    def test_financial_role_from_user_roles(self):
        assert auth.user_has_any_role(FINANCE, "finance", "executive")
        assert not auth.user_has_any_role(FINANCE, "executive")

    def test_base_role_counts(self):
        assert auth.user_has_any_role(PM, "project_manager")

    def test_slim_identity_without_roles_key(self):
        # Older tests inject dicts with only `role`; they must keep working.
        assert auth.user_has_any_role({"role": "admin"}, "finance")
        assert not auth.user_has_any_role({"role": "project_manager"}, "finance")

    def test_require_roles_raises_403(self):
        dep = auth.require_roles("finance")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(dep(user=PM))
        assert exc.value.status_code == 403

    def test_require_roles_returns_user(self):
        dep = auth.require_roles("finance")
        assert asyncio.run(dep(user=FINANCE)) is FINANCE


class TestLoadFinancialRoles:
    def test_merges_user_roles_and_base_role(self):
        db = MemDB({
            "user_roles": [
                {"user_id": "u1", "role": "executive", "revoked_at": None},
                {"user_id": "u1", "role": "finance", "revoked_at": "2026-01-01"},
                {"user_id": "u2", "role": "finance", "revoked_at": None},
            ],
            "users": [{"id": "u1", "is_employee": False}],
        })
        roles, emp = auth._load_financial_roles(db, {"id": "u1", "role": "project_manager"})
        assert roles == ["executive", "project_manager"]
        assert emp is False

    def test_failure_falls_back_to_base_role(self):
        db = MemDB()
        db.errors[("user_roles", "select")] = api_error("42P01", "relation does not exist")
        roles, emp = auth._load_financial_roles(db, {"id": "u1", "role": "admin"})
        assert roles == ["admin"] and emp is True


# ── invite metadata ──────────────────────────────────────────────────────────
class TestInviteMetadata:
    def test_unchanged_without_financial_fields(self):
        assert user_service._invite_metadata("A", "project_manager", [], True) == {
            "full_name": "A", "role": "project_manager"}

    def test_roles_and_external_flag(self):
        assert user_service._invite_metadata("A", "project_manager", ["finance", "executive"], False) == {
            "full_name": "A", "role": "project_manager",
            "roles": ["executive", "finance"], "is_employee": False}


# ── role assignment ──────────────────────────────────────────────────────────
class TestApplyFinancialRoles:
    def _db(self):
        return MemDB({
            "users": [{"id": "t1", "role": "project_manager", "is_employee": True}],
            "user_roles": [
                {"id": "r-base", "user_id": "t1", "role": "project_manager", "revoked_at": None},
                {"id": "r-fin", "user_id": "t1", "role": "finance", "revoked_at": None},
            ],
        })

    def test_grants_new_revokes_removed_keeps_base(self):
        db = self._db()
        user_service._apply_financial_roles(db, "t1", ["executive"], False, actor_id=ADMIN_ID)
        rows = {r["role"]: r for r in db.tables["user_roles"]}
        assert rows["finance"]["revoked_at"] is not None           # revoked, not deleted
        assert rows["project_manager"]["revoked_at"] is None        # base role untouched
        assert rows["executive"]["granted_by"] == ADMIN_ID          # granted
        assert db.tables["users"][0]["is_employee"] is False

    def test_idempotent(self):
        db = self._db()
        user_service._apply_financial_roles(db, "t1", ["finance"], None, actor_id=ADMIN_ID)
        assert len(db.tables["user_roles"]) == 2
        assert all(r["revoked_at"] is None for r in db.tables["user_roles"])


class TestRolesEndpoint:
    def test_unknown_user_is_404(self, fin_client):
        tc = fin_client(MemDB({"users": [], "user_roles": []}), ADMIN)
        resp = tc.put("/api/v1/users/00000000-0000-0000-0000-000000000001/roles",
                      json={"roles": ["executive", "finance"]})
        assert resp.status_code == 404

    def test_non_admin_forbidden(self, fin_client):
        tc = fin_client(MemDB(), PM)
        resp = tc.put("/api/v1/users/00000000-0000-0000-0000-000000000001/roles", json={"roles": []})
        assert resp.status_code == 403

    def test_rejects_unknown_role(self, fin_client):
        tc = fin_client(MemDB(), ADMIN)
        resp = tc.put("/api/v1/users/00000000-0000-0000-0000-000000000001/roles", json={"roles": ["god"]})
        assert resp.status_code == 422

    def test_returns_roles(self, fin_client, monkeypatch):
        uid = "00000000-0000-0000-0000-0000000000aa"
        db = MemDB({
            "users": [{"id": uid, "email": "t@x.test", "full_name": "T", "role": "project_manager",
                       "is_active": True, "invited_by": None, "deleted_at": None, "is_employee": True,
                       "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"}],
            "user_roles": [{"id": "b", "user_id": uid, "role": "project_manager", "revoked_at": None}],
        })
        monkeypatch.setattr(user_service, "_confirmed_at_by_id", lambda _db: {uid: "2026-01-02"})
        tc = fin_client(db, identity(ADMIN_ID, "admin"))
        resp = tc.put(f"/api/v1/users/{uid}/roles", json={"roles": ["executive"], "is_employee": False})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["roles"] == ["executive", "project_manager"]
        assert body["is_employee"] is False
        assert body["status"] == "active"
