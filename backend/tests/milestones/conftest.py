"""Shared fixtures for milestone endpoint tests (Phase 10.1).

Uses a hand-rolled fake Supabase client (`FakeDB`) rather than the live DB —
mirrors the mocked-Supabase convention in backend/tests/bid_template_freeze/.
The fake dispatches per-table so a single request can hit `contracts` (contract
gate) and `milestones` (sort_order lookup + insert) in one call.

Auth + db are injected via FastAPI dependency overrides.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app

# ── Deterministic IDs ──────────────────────────────────────────────────────

PM_USER_ID = uuid4()
TASK_ID = uuid4()
CONTRACT_ID = uuid4()
MILESTONE_ID = uuid4()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def milestone_row(**overrides) -> dict:
    """A full milestones row shaped like the DB response."""
    row = {
        "id": str(MILESTONE_ID),
        "task_id": str(TASK_ID),
        "contract_id": str(CONTRACT_ID),
        "name": "Foundation Pour",
        "start_date": "2026-08-01",
        "end_date": "2026-08-15",
        "actual_start_date": None,
        "actual_end_date": None,
        "status": "scheduled",
        "sort_order": 0,
        "notes": None,
        "created_by": str(PM_USER_ID),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    row.update(overrides)
    return row


# ── Fake Supabase client ────────────────────────────────────────────────────


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        if count is not None:
            self.count = count
        elif isinstance(data, list):
            self.count = len(data)
        else:
            self.count = 1 if data else 0


class _Query:
    """Chainable query recorder; terminal .execute() dispatches to the FakeDB."""

    def __init__(self, table: str, db: "FakeDB"):
        self._table = table
        self._db = db
        self._op = "select"
        self._select = None
        self._single = False
        self._payload = None

    def select(self, cols="*", **_kw):
        self._op, self._select = "select", cols
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, *_a, **_k):
        return self

    def neq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        return self._db._dispatch(
            self._table, self._op, self._select, self._single, self._payload
        )


class FakeDB:
    def __init__(
        self,
        *,
        contract_row: dict | None = None,
        existing_orders: list[int] | None = None,
        current_milestone: dict | None = None,
        milestone_missing: bool = False,
        delete_fk_violation: bool = False,
        insert_error: APIError | None = None,
    ):
        self.contract_row = contract_row
        self.existing_orders = existing_orders or []
        self.current_milestone = current_milestone
        self.milestone_missing = milestone_missing
        self.delete_fk_violation = delete_fk_violation
        self.insert_error = insert_error
        self.last_insert: dict | None = None
        self.last_update: dict | None = None
        self.deleted = False

    def table(self, name: str) -> _Query:
        return _Query(name, self)

    def _dispatch(self, table, op, select, single, payload):
        if table == "contracts":
            data = [self.contract_row] if self.contract_row else []
            return _Result(data)

        if table == "milestones":
            if op == "select":
                if single:
                    if self.milestone_missing:
                        raise APIError({"code": "PGRST116", "message": "0 rows returned"})
                    return _Result(self.current_milestone)
                # list select of sort_order for next_sort_order()
                return _Result([{"sort_order": o} for o in self.existing_orders])
            if op == "insert":
                if self.insert_error is not None:
                    raise self.insert_error
                self.last_insert = dict(payload)
                row = dict(payload)
                row.setdefault("id", str(MILESTONE_ID))
                row.setdefault("actual_start_date", None)
                row.setdefault("actual_end_date", None)
                row.setdefault("created_at", _now_iso())
                row.setdefault("updated_at", _now_iso())
                return _Result([row])
            if op == "update":
                self.last_update = dict(payload)
                merged = {**(self.current_milestone or milestone_row()), **payload}
                return _Result([merged])
            if op == "delete":
                if self.delete_fk_violation:
                    raise APIError({"code": "23503", "message": "violates foreign key constraint"})
                self.deleted = True
                return _Result([])

        return _Result([])


# ── FastAPI TestClient wiring ───────────────────────────────────────────────


@pytest.fixture()
def authed_user() -> dict:
    return {
        "user_id": str(PM_USER_ID),
        "email": "pm@example.com",
        "full_name": "PM User",
        "role": "project_manager",
        "is_active": True,
    }


def make_client(db: FakeDB, authed_user: dict) -> TestClient:
    app.dependency_overrides[get_current_active_user] = lambda: authed_user
    app.dependency_overrides[get_supabase] = lambda: db
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()
