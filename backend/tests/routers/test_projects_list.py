"""Archived visibility on the project list endpoint.

`GET /projects` hides archived projects by default, includes them alongside
active ones with `include_archived=true`, and returns *only* archived ones with
`archived_only=true`. The last mode exists so the frontend "Archived" filter can
show an archived-only view through the hardened endpoint instead of a second
Supabase query path.

The fake below applies the archived/deleted filters for real (it does not
rubber-stamp), so a regression that dropped the `archived_only` branch would
fail these tests rather than pass them.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app

USER = {
    "user_id": str(uuid4()),
    "email": "pm@example.com",
    "full_name": "PM",
    "role": "project_manager",
    "is_active": True,
}


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Not:
    """Supports the `.not_.is_(col, val)` chain as a negated filter."""

    def __init__(self, query: "_Query"):
        self._query = query

    def is_(self, col, val):
        self._query._filters.append(("not_is", col, val))
        return self._query


class _Query:
    def __init__(self, fake: "FakeDB", table: str):
        self._fake = fake
        self._table = table
        self._filters: list[tuple] = []
        self._want_count = False
        self._order: tuple | None = None
        self._range: tuple | None = None

    def select(self, *_a, count=None, **_k):
        if count == "exact":
            self._want_count = True
        return self

    @property
    def not_(self):
        return _Not(self)

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def ilike(self, col, pattern):
        self._filters.append(("ilike", col, pattern))
        return self

    def order(self, col, desc=False, **_k):
        self._order = (col, desc)
        return self

    def limit(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        return self._fake._resolve(self)


def _matches(row, filters) -> bool:
    for kind, col, val in filters:
        actual = row.get(col)
        if kind == "eq" and str(actual) != str(val):
            return False
        if kind == "is" and val == "null" and actual is not None:
            return False
        if kind == "not_is" and val == "null" and actual is None:
            return False
        if kind == "ilike":
            needle = str(val).strip("%").lower()
            if needle not in str(actual or "").lower():
                return False
    return True


class FakeDB:
    def __init__(self, projects: list[dict]):
        self.projects = projects

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def _resolve(self, q: _Query):
        rows = [r for r in self.projects if _matches(r, q._filters)]
        total = len(rows)
        if q._order:
            col, desc = q._order
            rows = sorted(rows, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        if q._range:
            start, end = q._range
            rows = rows[start : end + 1]
        return _Result(rows, count=total if q._want_count else None)


def _project(name: str, *, archived: bool = False, deleted: bool = False) -> dict:
    return {
        "id": str(uuid4()),
        "name": name,
        "description": None,
        "address": None,
        "city": None,
        "state": None,
        "zip_code": None,
        "latitude": None,
        "longitude": None,
        "budget": None,
        "status": "planning",
        "start_date": None,
        "estimated_end_date": None,
        "created_by": str(uuid4()),
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "deleted_at": "2026-01-01T00:00:00Z" if deleted else None,
        "archived_at": "2026-02-01T00:00:00Z" if archived else None,
        "archived_by": str(uuid4()) if archived else None,
    }


@pytest.fixture()
def client_with():
    def _bind(fake):
        app.dependency_overrides[get_current_active_user] = lambda: USER
        app.dependency_overrides[get_supabase] = lambda: fake
        return TestClient(app)

    yield _bind
    app.dependency_overrides.clear()


def _names(resp) -> set[str]:
    return {p["name"] for p in resp.json()["items"]}


class TestArchivedVisibility:
    def _fake(self) -> FakeDB:
        return FakeDB(
            [
                _project("Active One"),
                _project("Active Two"),
                _project("Archived One", archived=True),
                _project("Deleted One", deleted=True),
            ]
        )

    def test_default_hides_archived_and_deleted(self, client_with):
        resp = client_with(self._fake()).get("/api/v1/projects")
        assert resp.status_code == 200
        assert _names(resp) == {"Active One", "Active Two"}
        assert resp.json()["total"] == 2

    def test_include_archived_shows_active_and_archived(self, client_with):
        resp = client_with(self._fake()).get("/api/v1/projects?include_archived=true")
        assert resp.status_code == 200
        assert _names(resp) == {"Active One", "Active Two", "Archived One"}
        assert resp.json()["total"] == 3

    def test_archived_only_shows_just_archived(self, client_with):
        resp = client_with(self._fake()).get("/api/v1/projects?archived_only=true")
        assert resp.status_code == 200
        assert _names(resp) == {"Archived One"}
        assert resp.json()["total"] == 1

    def test_archived_only_overrides_include_archived(self, client_with):
        resp = client_with(self._fake()).get(
            "/api/v1/projects?archived_only=true&include_archived=false"
        )
        assert resp.status_code == 200
        assert _names(resp) == {"Archived One"}
