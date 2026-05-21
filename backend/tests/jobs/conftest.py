"""
Fixtures for scheduler / background-job tests.

The scheduler infrastructure is never started here — the revision-expiry job
body is exercised directly with a FakeSupabase double, and the health
endpoint reads only in-memory state. The real scheduler lifecycle runs via
the app lifespan, which these tests bypass.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.jobs import scheduler as scheduler_module
from app.main import app


# ── FakeSupabase: a minimal double for the chains expire_revision_requests uses ──
#
#   .table(t).select(...).eq(...).lt(...).execute()
#   .table(t).update(payload).eq(...).eq(...).execute()
#
# The SELECT on bid_revision_requests actually evaluates the eq/lt filters
# against `revision_rows`, so "future deadline" / "already declined" rows are
# genuinely filtered out. UPDATE results are configurable per id to simulate
# the TOCTOU lost-race case.


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, fake: "FakeSupabase", table: str):
        self._fake = fake
        self._table = table
        self._op = "select"
        self._payload = None
        self._eq: dict = {}
        self._lt: dict = {}

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def lt(self, col, val):
        self._lt[col] = val
        return self

    def execute(self):
        return self._fake._resolve(
            self._table, self._op, self._eq, self._lt, self._payload
        )


class FakeSupabase:
    def __init__(self, revision_rows=None, update_results=None):
        # Full bid_revision_requests rows; the SELECT filters these.
        self.revision_rows = revision_rows or []
        # id -> data list returned by the bid_revision_requests UPDATE.
        # A missing id defaults to success ([{"id": id}]); [] = TOCTOU loss.
        self.update_results = update_results or {}
        # Recorded writes, for assertions.
        self.revision_updates: list[tuple] = []   # (id, payload)
        self.token_revocations: list[tuple] = []  # (bid_revision_request_id, payload)

    def table(self, name):
        return _Query(self, name)

    def _resolve(self, table, op, eq, lt, payload):
        if table == "bid_revision_requests" and op == "select":
            matched = []
            for row in self.revision_rows:
                if all(row.get(c) == v for c, v in eq.items()) and all(
                    row.get(c) is not None and row.get(c) < v for c, v in lt.items()
                ):
                    matched.append(
                        {"id": row["id"], "bid_invitation_id": row.get("bid_invitation_id")}
                    )
            return _Result(matched)

        if table == "bid_revision_requests" and op == "update":
            rid = eq.get("id")
            self.revision_updates.append((rid, payload))
            if rid in self.update_results:
                return _Result(self.update_results[rid])
            return _Result([{"id": rid}])  # default: guarded UPDATE succeeded

        if table == "magic_link_tokens" and op == "update":
            self.token_revocations.append((eq.get("bid_revision_request_id"), payload))
            return _Result([{"id": "token"}])

        return _Result([])


@pytest.fixture()
def make_fake_db():
    """Factory for a FakeSupabase configured per test."""

    def _make(revision_rows=None, update_results=None) -> FakeSupabase:
        return FakeSupabase(revision_rows=revision_rows, update_results=update_results)

    return _make


# ── Scheduler-health endpoint fixtures ──────────────────────────────────────

ADMIN_USER = {
    "user_id": "00000000-0000-0000-0000-000000000001",
    "email": "admin@example.com",
    "full_name": "Admin User",
    "role": "admin",
    "is_active": True,
}


@pytest.fixture()
def clear_last_run():
    """Reset the scheduler's in-memory last-run state around each test."""
    scheduler_module._last_run.clear()
    yield
    scheduler_module._last_run.clear()


@pytest.fixture()
def authed_client():
    """
    TestClient with auth overridden. Built without the `with` context
    manager so the lifespan does not run — the scheduler stays off.
    """
    app.dependency_overrides[get_current_active_user] = lambda: ADMIN_USER
    yield TestClient(app)
    app.dependency_overrides.clear()
