"""Fixtures for the holiday calendar suite.

Two styles live here, deliberately.

The calendar RULES are SQL-resident — the guardrail trigger and the three
business-day functions — so the tests that cover them hit the REAL database via
the session `client` fixture. Mocking them would only assert that the mock
matches itself.

Authorization and error MAPPING are Python, so those tests use dependency
overrides and a fake db, needing no database at all.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.core.time import business_today
from app.main import app

PM_ID = "22222222-2222-4222-8222-222222222222"


# ── Real-DB fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def sb(client: TestClient):
    """The app's service_role Supabase client (no second connection)."""
    return client.app.state.supabase


@pytest.fixture()
def holiday_sandbox(sb):
    """Records holidays inserted by a test and removes them on teardown.

    Refuses a past date. A past-dated row cannot be created through the guardrail
    trigger and cannot be deleted back out either, so leaking one would need a
    superuser to clean up.
    """
    created: list[str] = []
    today = business_today()

    class Sandbox:
        def add(self, d: date, name: str = "Test Holiday", source: str = "manual"):
            assert d > today, f"refusing to plant a past/today holiday on {d}"
            iso = d.isoformat()
            resp = (
                sb.table("holidays")
                .insert({"holiday_date": iso, "name": name, "source": source})
                .execute()
            )
            created.append(iso)
            return resp.data[0]

        def track(self, d: date | str) -> None:
            """Register a date written by the code under test, so teardown gets it."""
            created.append(d if isinstance(d, str) else d.isoformat())

    try:
        yield Sandbox()
    finally:
        for iso in created:
            try:
                sb.table("holidays").delete().eq("holiday_date", iso).execute()
            except APIError:  # pragma: no cover - best-effort cleanup
                pass


@pytest.fixture()
def future_anchor(sb) -> date:
    """A far-future Monday with no holidays within +/- 21 days.

    Far future so nothing collides with the guardrail's past-date freeze, and
    clear of existing rows so a planted holiday is the only one in the window.
    The window is three weeks either side because the contiguous-run test plants
    a two-week block and needs the surrounding days empty. Self-heals as the real
    calendar fills up.
    """
    cursor = business_today() + timedelta(days=60)
    cursor += timedelta(days=(7 - cursor.weekday()) % 7)  # forward to a Monday

    for _ in range(52):
        lo = (cursor - timedelta(days=21)).isoformat()
        hi = (cursor + timedelta(days=21)).isoformat()
        hit = (
            sb.table("holidays")
            .select("id")
            .gte("holiday_date", lo)
            .lte("holiday_date", hi)
            .limit(1)
            .execute()
        )
        if not (hit.data or []):
            return cursor
        cursor += timedelta(days=7)

    pytest.skip("no clear 3-week window found in the next year of the calendar")


# ── Fake-DB fixtures ────────────────────────────────────────────────────────


def make_api_error(code: str, message: str = "") -> APIError:
    """Build a postgrest APIError carrying a SQLSTATE-like code (e.g. 'PT422')."""
    return APIError({"code": code, "message": message or code})


class RecordingDB:
    """Minimal fake: records calls, optionally raises a preloaded APIError.

    Only implements the surface holiday_service touches.
    """

    def __init__(self, *, error: APIError | None = None, rows: list | None = None):
        self.error = error
        self.rows = rows if rows is not None else [{"id": "x"}]
        self.inserts: list[dict] = []
        self.rpc_calls: list[tuple[str, dict]] = []

    # table(...) chain
    def table(self, name: str):
        self._table = name
        return self

    def insert(self, payload):
        self.inserts.append(payload)
        return self

    def update(self, payload):
        self.inserts.append(payload)
        return self

    def delete(self):
        return self

    def eq(self, *_args):
        return self

    def rpc(self, fn: str, params: dict):
        self.rpc_calls.append((fn, params))
        return self

    def execute(self):
        if self.error:
            raise self.error
        return type("Resp", (), {"data": self.rows})()


def _identity(user_id: str, role: str) -> dict:
    return {
        "user_id": user_id,
        "email": f"{role}@bluonx.dev",
        "full_name": role,
        "role": role,
        "is_active": True,
    }


@pytest.fixture()
def pm_client():
    """Factory: a TestClient acting as a project_manager (for authz tests).

    Overrides get_current_active_user, which require_admin depends on, so
    require_admin itself still runs for real.
    """

    def _make(db=None) -> TestClient:
        app.dependency_overrides[get_current_active_user] = lambda: _identity(
            PM_ID, "project_manager"
        )
        app.dependency_overrides[get_supabase] = lambda: db or RecordingDB()
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_fake_client():
    """Factory: a TestClient acting as an admin against a RecordingDB."""

    def _make(db: RecordingDB) -> TestClient:
        app.dependency_overrides[get_current_active_user] = lambda: _identity(
            "11111111-1111-4111-8111-111111111111", "admin"
        )
        app.dependency_overrides[get_supabase] = lambda: db
        tc = TestClient(app)
        tc.db = db
        return tc

    yield _make
    app.dependency_overrides.clear()
