"""Tests for the daily_insurance_expiration job (Task 7.5).

Calls the inner `run_daily_insurance_expiration` directly so the
@tracked_job decorator is bypassed and counts can be asserted without
mucking with scheduler state. NotificationService's `create_notification`
is injected as a Mock so we can both observe calls and induce failures.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.jobs.insurance_expiration import run_daily_insurance_expiration


# ── Fake supabase that handles the chains the worker builds ──────────────


class _Result:
    def __init__(self, data):
        self.data = data


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
        self._op = "select"
        self._filters: list[tuple] = []

    def select(self, *_a, **_k):
        self._op = "select"
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
    def __init__(
        self,
        *,
        vendors: list[dict] | None = None,
        admins: list[dict] | None = None,
        notifications: list[dict] | None = None,
    ):
        self.vendors = vendors or []
        self.admins = admins or []
        self.notifications = notifications or []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def _resolve(self, q: _Query):
        if q._table == "vendors" and q._op == "select":
            rows = [v for v in self.vendors if _matches(v, q._filters)]
            return _Result(rows)
        if q._table == "users" and q._op == "select":
            rows = [u for u in self.admins if _matches(u, q._filters)]
            return _Result(rows)
        if q._table == "notifications" and q._op == "select":
            rows = [n for n in self.notifications if _matches(n, q._filters)]
            return _Result(rows)
        return _Result([])


# ── Helpers ──────────────────────────────────────────────────────────────


def _vendor(*, expiration: date | None, name: str = "Acme Co.", deleted: bool = False):
    return {
        "id": str(uuid4()),
        "company_name": name,
        "insurance_expiration_date": expiration.isoformat() if expiration else None,
        "deleted_at": "2026-01-01T00:00:00Z" if deleted else None,
    }


def _admin(*, name: str = "Admin"):
    return {
        "id": str(uuid4()),
        "email": f"{name.lower()}@example.com",
        "full_name": name,
        "role": "admin",
        "is_active": True,
        "deleted_at": None,
    }


def _run(db, notification_creator=None) -> dict:
    return asyncio.run(
        run_daily_insurance_expiration(
            db, notification_creator=notification_creator or MagicMock(return_value={"id": "n"})
        )
    )


# ── Tests ────────────────────────────────────────────────────────────────


class TestRunDailyInsuranceExpiration:
    def test_no_matching_records_returns_zeros(self):
        db = FakeDB(vendors=[], admins=[_admin()])
        result = _run(db)
        assert result["expiring_30day_notified"] == 0
        assert result["expiring_7day_notified"] == 0
        assert result["expired_notified"] == 0
        assert result["deduplicated_skipped"] == 0
        assert "duration_seconds" in result

    def test_t_minus_30_creates_expiring_notification(self):
        today = date.today()
        vendor = _vendor(expiration=today + timedelta(days=30))
        admin_a, admin_b = _admin(name="Alice"), _admin(name="Bob")
        db = FakeDB(vendors=[vendor], admins=[admin_a, admin_b])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["expiring_30day_notified"] == 2
        assert result["deduplicated_skipped"] == 0
        assert mock.call_count == 2
        call_kwargs = [c.kwargs for c in mock.call_args_list]
        types = {kw["notification_type"] for kw in call_kwargs}
        assert types == {"insurance_expiring"}

    def test_t_minus_7_creates_expiring_notification(self):
        today = date.today()
        vendor = _vendor(expiration=today + timedelta(days=7))
        db = FakeDB(vendors=[vendor], admins=[_admin()])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["expiring_7day_notified"] == 1
        assert result["expiring_30day_notified"] == 0
        assert mock.call_args.kwargs["notification_type"] == "insurance_expiring"

    def test_expired_creates_expired_notification(self):
        today = date.today()
        vendor = _vendor(expiration=today - timedelta(days=5))
        db = FakeDB(vendors=[vendor], admins=[_admin()])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["expired_notified"] == 1
        kw = mock.call_args.kwargs
        assert kw["notification_type"] == "insurance_expired"
        assert "Expired 5 day(s) ago." in kw["message"]

    def test_dedupe_skips_unread_existing(self):
        today = date.today()
        vendor = _vendor(expiration=today + timedelta(days=30))
        admin = _admin()
        existing = {
            "id": str(uuid4()),
            "user_id": admin["id"],
            "notification_type": "insurance_expiring",
            "reference_type": "vendors",
            "reference_id": vendor["id"],
            "is_read": False,
        }
        db = FakeDB(vendors=[vendor], admins=[admin], notifications=[existing])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["deduplicated_skipped"] == 1
        assert result["expiring_30day_notified"] == 0
        mock.assert_not_called()

    def test_dates_outside_tiers_are_skipped(self):
        today = date.today()
        vendor = _vendor(expiration=today + timedelta(days=15))  # in window, no tier
        db = FakeDB(vendors=[vendor], admins=[_admin()])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert sum(
            result[k]
            for k in (
                "expiring_30day_notified",
                "expiring_7day_notified",
                "expired_notified",
                "deduplicated_skipped",
            )
        ) == 0
        mock.assert_not_called()

    def test_deleted_vendor_excluded(self):
        today = date.today()
        active = _vendor(expiration=today + timedelta(days=30), name="Active Co.")
        gone = _vendor(
            expiration=today + timedelta(days=30), name="Deleted Co.", deleted=True
        )
        db = FakeDB(vendors=[active, gone], admins=[_admin()])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["expiring_30day_notified"] == 1
        assert mock.call_count == 1
        assert "Active Co." in mock.call_args.kwargs["title"]

    def test_single_admin_failure_does_not_crash_job(self):
        today = date.today()
        vendor = _vendor(expiration=today + timedelta(days=30))
        admins = [_admin(name=f"Admin{i}") for i in range(3)]
        db = FakeDB(vendors=[vendor], admins=admins)

        # Fail on the second call, succeed on the others.
        calls = {"n": 0}

        def flaky(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("simulated supabase failure")
            return {"id": "n"}

        mock = MagicMock(side_effect=flaky)
        result = _run(db, notification_creator=mock)

        # Three attempts; two successful sends counted.
        assert mock.call_count == 3
        assert result["expiring_30day_notified"] == 2
        assert result["deduplicated_skipped"] == 0
        # No exception escaped the worker.
        assert "duration_seconds" in result

    def test_notification_payload_shape(self):
        today = date.today()
        vendors = [
            _vendor(expiration=today + timedelta(days=30), name="V30"),
            _vendor(expiration=today + timedelta(days=7), name="V7"),
            _vendor(expiration=today - timedelta(days=5), name="V5"),
        ]
        db = FakeDB(vendors=vendors, admins=[_admin()])
        mock = MagicMock(return_value={"id": "n"})

        _run(db, notification_creator=mock)

        by_title = {c.kwargs["title"]: c.kwargs for c in mock.call_args_list}
        assert "Insurance expiring in 30 days: V30" in by_title
        assert "Insurance expiring in 7 days: V7" in by_title
        assert "Insurance expired: V5" in by_title

        assert "Expires in 30 days." in by_title["Insurance expiring in 30 days: V30"]["message"]
        assert "Expires in 7 days." in by_title["Insurance expiring in 7 days: V7"]["message"]
        assert "Expired 5 day(s) ago." in by_title["Insurance expired: V5"]["message"]

        # All notifications scoped to vendors.
        for kw in mock.call_args_list:
            assert kw.kwargs["reference_type"] == "vendors"
