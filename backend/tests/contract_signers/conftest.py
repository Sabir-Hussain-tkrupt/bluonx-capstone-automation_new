"""
Isolated fixtures for the contract-signers admin suite.

No live Supabase. We override `get_current_active_user` (the caller identity that
`require_admin` reads) and `get_supabase` (a filter-aware fake client). The fake
honours .eq/.neq/.is_ filters against an in-memory `contract_signers` dataset so a
single seeded list drives both the duplicate-email probe and the active-signer
count the way the real DB would, and writes mutate that dataset so a read-after-write
reflects the change. Mirrors backend/tests/user_management/conftest.py.

spec keys:
  signers:  list[dict]  seed rows for contract_signers (mutated by writes)
  raise_on: dict like {"contract_signers": {"insert": APIError(...)}}  inject a write error
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app

ADMIN_ID = str(uuid4())
PM_ID = str(uuid4())


# ── row helper ───────────────────────────────────────────────────────────────
def signer_row(**overrides) -> dict:
    """A complete contract_signers row with sane defaults. Override per test.

    One builder for the whole suite — the user-management tests grew three
    near-identical local builders; that is not repeated here.
    """
    base = {
        "id": str(uuid4()),
        "full_name": "Dana Reyes",
        "email": "dana@bluonx.dev",
        "title": "VP of Development",
        "user_id": None,
        "is_active": True,
        "created_at": "2026-07-01T00:00:00+00:00",
        "updated_at": "2026-07-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def unique_violation() -> APIError:
    """The 23505 Postgres raises when contract_signers.email collides."""
    return APIError(
        {
            "code": "23505",
            "message": 'duplicate key value violates unique constraint "contract_signers_email_key"',
        }
    )


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
            stored = []
            for p in payloads:
                row = signer_row(**p)
                self._rows.append(row)
                stored.append(dict(row))
            return _Result(stored)

        if self._op == "delete":
            self._maybe_raise_write()
            affected = [r for r in self._rows if self._match(r)]
            self._rows[:] = [r for r in self._rows if not self._match(r)]
            return _Result([dict(r) for r in affected])

        return _Result([])


def make_db(spec: dict) -> MagicMock:
    rows = [dict(r) for r in spec.get("signers", [])]
    write_errors = spec.get("raise_on", {}).get("contract_signers", {})

    client = MagicMock()

    def _table(name: str):
        if name != "contract_signers":
            # No other table is touched by contract_signer_service; fail loudly.
            raise AssertionError(f"unexpected table access: {name}")
        return _Query(rows, write_errors)

    client.table.side_effect = _table
    # Exposed so a test can assert on the post-request dataset.
    client.rows = rows
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
    """Factory: build a TestClient acting as an admin against the given spec.

    The fake db is attached as `tc.db` so tests can inspect `tc.db.rows` after
    the request."""

    def _make(spec: dict | None = None) -> TestClient:
        db = make_db(spec or {})
        app.dependency_overrides[get_current_active_user] = lambda: _identity(
            ADMIN_ID, "admin", "admin@bluonx.dev"
        )
        app.dependency_overrides[get_supabase] = lambda: db
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
        tc = TestClient(app)
        tc.db = db
        return tc

    yield _make
    app.dependency_overrides.clear()
