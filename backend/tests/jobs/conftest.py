"""
Fixtures for scheduler / background-job tests.

The scheduler infrastructure is never started here — the revision-expiry job
body is exercised directly with a FakeSupabase double, and the health
endpoint reads only in-memory state. The real scheduler lifecycle runs via
the app lifespan, which these tests bypass.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.jobs import scheduler as scheduler_module
from app.main import app
from app.services.email_service import EmailSendResult


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


# ── FakeReminderDB: double for the bid-reminders job (Task 7.3) ─────────────
#
# The bid-reminders job issues read chains the FakeSupabase above cannot
# serve — a joined bid_invitations query, an email_log dedup query, and a
# per-invitation status re-read — using operators (.in_, .not_.in_, .gte,
# .maybe_single) it does not implement. FakeReminderDB is a separate,
# self-contained double for that job.
#
# `invitation_rows` are PostgREST-joined shapes (top-level invitation fields
# plus nested bid_packages -> tasks -> projects, bid_packages.users,
# vendor_contacts, vendors). `email_log_rows` back the dedup query.
# `status_overrides` (invitation id -> status) makes the per-invitation
# re-read disagree with the bulk query, simulating a status change between
# query and send.


def _dotted_get(row: dict, col: str):
    """Resolve a possibly-dotted column name against a (possibly nested) row."""
    cur = row
    for part in col.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _row_matches(row: dict, filters: list) -> bool:
    """Evaluate the accumulated query predicates against one row."""
    for kind, col, val in filters:
        actual = _dotted_get(row, col)
        if kind == "eq" and actual != val:
            return False
        if kind == "in" and actual not in val:
            return False
        if kind == "not_in" and actual in val:
            return False
        if kind == "gte" and (actual is None or actual < val):
            return False
        if kind == "lt" and (actual is None or actual >= val):
            return False
    return True


class _ReminderResult:
    def __init__(self, data):
        self.data = data


class _ReminderNot:
    """Captures `.not_.in_(...)` as a negated filter."""

    def __init__(self, query: "_ReminderQuery"):
        self._query = query

    def in_(self, col, vals):
        self._query._filters.append(("not_in", col, list(vals)))
        return self._query


class _ReminderQuery:
    """Fluent stub for the supabase-py read chains run_daily_bid_reminders uses."""

    def __init__(self, fake: "FakeReminderDB", table: str):
        self._fake = fake
        self._table = table
        self._filters: list = []
        self._single = False

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def gte(self, col, val):
        self._filters.append(("gte", col, val))
        return self

    def lt(self, col, val):
        self._filters.append(("lt", col, val))
        return self

    @property
    def not_(self):
        return _ReminderNot(self)

    def maybe_single(self):
        self._single = True
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        return self._fake._resolve(self._table, self._filters, self._single)


class FakeReminderDB:
    def __init__(self, invitation_rows=None, email_log_rows=None,
                 status_overrides=None):
        self.invitation_rows = invitation_rows or []
        self.email_log_rows = email_log_rows or []
        self.status_overrides = status_overrides or {}

    def table(self, name):
        return _ReminderQuery(self, name)

    def _resolve(self, table, filters, single):
        if table == "bid_invitations" and single:
            # Per-invitation status re-read.
            inv_id = next(
                (v for k, c, v in filters if k == "eq" and c == "id"), None
            )
            row = next(
                (r for r in self.invitation_rows if r.get("id") == inv_id), None
            )
            if row is None:
                return _ReminderResult(None)
            status = self.status_overrides.get(inv_id, row.get("status"))
            return _ReminderResult({"status": status})

        if table == "bid_invitations":
            return _ReminderResult(
                [r for r in self.invitation_rows if _row_matches(r, filters)]
            )

        if table == "email_log":
            return _ReminderResult(
                [r for r in self.email_log_rows if _row_matches(r, filters)]
            )

        return _ReminderResult([])


@pytest.fixture()
def make_reminder_db():
    """Factory for a FakeReminderDB configured per test."""

    def _make(invitation_rows=None, email_log_rows=None, status_overrides=None):
        return FakeReminderDB(
            invitation_rows=invitation_rows,
            email_log_rows=email_log_rows,
            status_overrides=status_overrides,
        )

    return _make


@pytest.fixture()
def mock_email_service() -> AsyncMock:
    """AsyncMock EmailService whose send_email succeeds for every call."""
    service = AsyncMock()
    service.send_email.return_value = EmailSendResult(
        message_id="mock-msg", status="sent", error=None
    )
    return service


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
