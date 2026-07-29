"""
Isolated fixtures for the admin user-management suite.

No live Supabase. We override `get_current_active_user` (the caller identity that
`require_admin` reads) and `get_supabase` (a filter-aware fake client), and stub
`client.auth.admin.*`. The fake honours .eq/.is_/.neq filters against an in-memory
`users` dataset so a single seeded list drives both the target fetch and the
last-admin count the way the real DB would, and writes mutate that dataset so a
read-after-write reflects the change.

spec keys:
  users:         list[dict]  seed rows for public.users (mutated by writes)
  confirmed:     dict[str, str|None]  auth-user id -> confirmed_at (absent => pending)
  invite_result: object|Exception  return value / side effect of invite_user_by_email
  raise_on:      dict like {"users": {"update": APIError(...)}}  inject a write error
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.core.auth import get_current_active_user
from app.core.rate_limit import validate_token_rate_limit
from app.core.supabase_client import get_supabase
from app.main import app

ADMIN_ID = str(uuid4())
OTHER_ADMIN_ID = str(uuid4())
PM_ID = str(uuid4())


# ── row helpers ──────────────────────────────────────────────────────────────
def user_row(**overrides) -> dict:
    """A complete public.users row with sane defaults. Override per test."""
    base = {
        "id": str(uuid4()),
        "email": "person@bluonx.dev",
        "full_name": "Person",
        "role": "project_manager",
        "is_active": True,
        "invited_by": None,
        "created_at": "2026-07-01T00:00:00+00:00",
        "updated_at": "2026-07-01T00:00:00+00:00",
        "deleted_at": None,
    }
    base.update(overrides)
    return base


def admin_row(**overrides) -> dict:
    return user_row(**{"role": "admin", "email": "admin@bluonx.dev", **overrides})


# ── filter-aware fake query ──────────────────────────────────────────────────
class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows: list[dict], write_errors: dict):
        self._rows = rows
        self._write_errors = write_errors
        self._op = "select"
        self._filters: list[tuple] = []
        self._single = False
        self._payload = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, payload, *_a, **_k):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload, *_a, **_k):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self, *_a, **_k):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, vals))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def single(self):
        self._single = "strict"
        return self

    def maybe_single(self):
        self._single = "maybe"
        return self

    def _match(self, row: dict) -> bool:
        for kind, col, val in self._filters:
            cell = row.get(col)
            if kind == "eq" and str(cell) != str(val):
                return False
            if kind == "neq" and str(cell) == str(val):
                return False
            if kind == "in" and cell not in val:
                return False
            if kind == "is":
                if val in ("null", None):
                    if cell is not None:
                        return False
                elif cell != val:
                    return False
        return True

    def _maybe_raise_write(self):
        err = self._write_errors.get(self._op)
        if err is not None:
            raise err

    def execute(self, *_a, **_k):
        if self._op == "select":
            matched = [dict(r) for r in self._rows if self._match(r)]
            if self._single:
                if not matched:
                    if self._single == "maybe":
                        return _Result(None)
                    raise APIError({"code": "PGRST116", "message": "no rows"})
                return _Result(matched[0])
            return _Result(matched)

        if self._op == "update":
            self._maybe_raise_write()
            affected = [r for r in self._rows if self._match(r)]
            for r in affected:
                r.update(self._payload)
            return _Result([dict(r) for r in affected])

        if self._op == "insert":
            self._maybe_raise_write()
            payloads = (
                self._payload if isinstance(self._payload, list) else [self._payload]
            )
            for p in payloads:
                self._rows.append(dict(p))
            return _Result([dict(p) for p in payloads])

        if self._op == "delete":
            self._maybe_raise_write()
            affected = [r for r in self._rows if self._match(r)]
            self._rows[:] = [r for r in self._rows if not self._match(r)]
            return _Result([dict(r) for r in affected])

        return _Result([])


def _build_auth_admin(spec: dict, user_ids: list[str]) -> MagicMock:
    confirmed = spec.get("confirmed", {})
    admin = MagicMock()

    # invite_user_by_email
    inv = spec.get("invite_result")
    if isinstance(inv, Exception):
        admin.invite_user_by_email.side_effect = inv
    elif inv is not None:
        admin.invite_user_by_email.return_value = inv
    else:
        admin.invite_user_by_email.return_value = SimpleNamespace(
            user=SimpleNamespace(id=str(uuid4()), confirmed_at=None)
        )

    # get_user_by_id -> UserResponse-like with .user.confirmed_at
    def _get_user_by_id(uid, *_a, **_k):
        return SimpleNamespace(
            user=SimpleNamespace(id=str(uid), confirmed_at=confirmed.get(str(uid)))
        )

    admin.get_user_by_id.side_effect = _get_user_by_id

    # list_users -> page 1 has everyone, later pages empty
    ids = list(dict.fromkeys([str(i) for i in user_ids] + list(confirmed.keys())))

    def _list_users(page=None, per_page=None):
        if (page or 1) != 1:
            return []
        return [
            SimpleNamespace(id=i, confirmed_at=confirmed.get(i)) for i in ids
        ]

    admin.list_users.side_effect = _list_users
    return admin


def make_db(spec: dict) -> MagicMock:
    rows = [dict(r) for r in spec.get("users", [])]
    write_errors = spec.get("raise_on", {}).get("users", {})

    client = MagicMock()

    def _table(name: str):
        if name != "users":
            # No other table is touched by user_service; fail loudly if it is.
            raise AssertionError(f"unexpected table access: {name}")
        return _Query(rows, write_errors)

    client.table.side_effect = _table
    client.auth.admin = _build_auth_admin(spec, [r["id"] for r in rows])
    return client


# ── identities ───────────────────────────────────────────────────────────────
def _identity(user_id: str, role: str, email: str) -> dict:
    return {
        "user_id": user_id,
        "email": email,
        "full_name": role.title(),
        "role": role,
        "is_active": True,
    }


@pytest.fixture()
def admin_client():
    """Factory: build a TestClient acting as ADMIN_ID against the given spec.

    The fake db is built once and attached as `tc.db` so tests can assert on the
    auth-admin mock (e.g. invite call args) after the request."""

    def _make(spec: dict) -> TestClient:
        db = make_db(spec)
        app.dependency_overrides[get_current_active_user] = lambda: _identity(
            ADMIN_ID, "admin", "admin@bluonx.dev"
        )
        app.dependency_overrides[get_supabase] = lambda: db
        app.dependency_overrides[validate_token_rate_limit] = lambda: None
        tc = TestClient(app)
        tc.db = db
        return tc

    yield _make
    app.dependency_overrides.clear()


@pytest.fixture()
def pm_client():
    """Factory: build a TestClient acting as a project_manager (for authz tests)."""

    def _make(spec: dict | None = None) -> TestClient:
        db = make_db(spec or {})
        app.dependency_overrides[get_current_active_user] = lambda: _identity(
            PM_ID, "project_manager", "pm@bluonx.dev"
        )
        app.dependency_overrides[get_supabase] = lambda: db
        app.dependency_overrides[validate_token_rate_limit] = lambda: None
        tc = TestClient(app)
        tc.db = db
        return tc

    yield _make
    app.dependency_overrides.clear()
