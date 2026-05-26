"""Tests for GET /api/v1/vendors/insurance-expiring-count (Task 7.5)."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app


USER = {
    "user_id": str(uuid4()),
    "email": "admin@example.com",
    "full_name": "Admin",
    "role": "admin",
    "is_active": True,
}


# ── Fake supabase with count="exact" support ─────────────────────────────


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _NotIs:
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

    def select(self, *_a, count=None, **_k):
        if count == "exact":
            self._want_count = True
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    @property
    def not_(self) -> _NotIs:
        return _NotIs(self)

    def lte(self, col, val):
        self._filters.append(("lte", col, val))
        return self

    def execute(self):
        return self._fake._resolve(self)


def _matches(row, filters):
    for kind, col, val in filters:
        actual = row.get(col)
        if kind == "eq" and actual != val:
            return False
        if kind == "is":
            if val == "null" and actual is not None:
                return False
            if val != "null" and actual is None:
                return False
        if kind == "not_is":
            if val == "null" and actual is None:
                return False
        if kind == "lte" and (actual is None or str(actual) > str(val)):
            return False
    return True


class FakeDB:
    def __init__(self, *, vendors: list[dict] | None = None):
        self.vendors = vendors or []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def _resolve(self, q: _Query):
        if q._table == "vendors":
            rows = [v for v in self.vendors if _matches(v, q._filters)]
            return _Result(rows, count=len(rows) if q._want_count else None)
        return _Result([])


def _vendor(*, expiration: date | None, deleted: bool = False):
    return {
        "id": str(uuid4()),
        "insurance_expiration_date": expiration.isoformat() if expiration else None,
        "deleted_at": "2026-01-01T00:00:00Z" if deleted else None,
    }


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def client_with():
    def _bind(fake):
        app.dependency_overrides[get_current_active_user] = lambda: USER
        app.dependency_overrides[get_supabase] = lambda: fake
        return TestClient(app)

    yield _bind
    app.dependency_overrides.clear()


# ── Tests ────────────────────────────────────────────────────────────────


class TestInsuranceExpiringCount:
    def test_count_zero_when_no_matches(self, client_with):
        client = client_with(FakeDB(vendors=[]))
        resp = client.get("/api/v1/vendors/insurance-expiring-count")
        assert resp.status_code == 200
        assert resp.json() == {"count": 0}

    def test_count_includes_expiring_within_30(self, client_with):
        today = date.today()
        fake = FakeDB(
            vendors=[
                _vendor(expiration=today + timedelta(days=30)),
                _vendor(expiration=today + timedelta(days=7)),
                _vendor(expiration=today + timedelta(days=15)),
            ]
        )
        client = client_with(fake)
        resp = client.get("/api/v1/vendors/insurance-expiring-count")
        assert resp.status_code == 200
        assert resp.json() == {"count": 3}

    def test_count_includes_expired(self, client_with):
        today = date.today()
        fake = FakeDB(vendors=[_vendor(expiration=today - timedelta(days=5))])
        client = client_with(fake)
        resp = client.get("/api/v1/vendors/insurance-expiring-count")
        assert resp.status_code == 200
        assert resp.json() == {"count": 1}

    def test_count_excludes_deleted_vendors(self, client_with):
        today = date.today()
        fake = FakeDB(
            vendors=[
                _vendor(expiration=today + timedelta(days=7), deleted=True),
                _vendor(expiration=today + timedelta(days=7), deleted=False),
            ]
        )
        client = client_with(fake)
        resp = client.get("/api/v1/vendors/insurance-expiring-count")
        assert resp.status_code == 200
        assert resp.json() == {"count": 1}

    def test_count_excludes_vendors_with_null_insurance_date(self, client_with):
        today = date.today()
        fake = FakeDB(
            vendors=[
                _vendor(expiration=None),
                _vendor(expiration=today + timedelta(days=10)),
            ]
        )
        client = client_with(fake)
        resp = client.get("/api/v1/vendors/insurance-expiring-count")
        assert resp.status_code == 200
        assert resp.json() == {"count": 1}
