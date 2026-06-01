"""Tests for the scheduler_self_check job (Task 7.8).

Calls the inner ``run_daily_scheduler_self_check`` directly so the
@tracked_job decorator is bypassed and counts can be asserted without
mucking with scheduler state. ``create_notification`` is injected as a
MagicMock so we can both observe call kwargs and induce failures.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.jobs import scheduler as scheduler_module
from app.jobs.scheduler_self_check import run_daily_scheduler_self_check


# ── Fake supabase ────────────────────────────────────────────────────────


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, fake: "FakeDB", table: str):
        self._fake = fake
        self._table = table
        self._op = "select"
        self._payload = None
        self._filters: list[tuple] = []

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def execute(self):
        return self._fake._resolve(self)


def _matches(row: dict, filters: list) -> bool:
    for kind, col, val in filters:
        actual = row.get(col)
        if kind == "eq" and actual != val:
            return False
        if kind == "in" and actual not in val:
            return False
        if kind == "is":
            if val == "null" and actual is not None:
                return False
            if val != "null" and actual is None:
                return False
    return True


class FakeDB:
    def __init__(
        self,
        *,
        users: list[dict] | None = None,
        notifications: list[dict] | None = None,
    ):
        self.users = users or []
        self.notifications = notifications or []
        self.inserts: list[dict] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def _resolve(self, q: _Query):
        if q._op == "select":
            if q._table == "users":
                return _Result([r for r in self.users if _matches(r, q._filters)])
            if q._table == "notifications":
                return _Result(
                    [r for r in self.notifications if _matches(r, q._filters)]
                )
            return _Result([])
        if q._op == "insert" and q._table == "notifications":
            self.inserts.append(dict(q._payload))
            return _Result([dict(q._payload)])
        return _Result([])


# ── Helpers ──────────────────────────────────────────────────────────────


def _admin(*, name: str = "Admin") -> dict:
    return {
        "id": str(uuid4()),
        "email": f"{name.lower()}@example.com",
        "full_name": name,
        "role": "admin",
        "is_active": True,
        "deleted_at": None,
    }


def _set_last_run(job_id: str, last_run_at: datetime | None) -> None:
    """Seed scheduler._last_run with an entry for `job_id`."""
    iso = last_run_at.isoformat() if last_run_at else None
    scheduler_module._last_run[job_id] = {
        "last_run_at": iso,
        "status": "success",
        "result": {},
        "error": None,
    }


def _seed_fresh(now: datetime) -> None:
    """Seed all four evaluated jobs with a recent last_run_at so nothing is stale."""
    _set_last_run("revision_expiry", now - timedelta(minutes=15))
    _set_last_run("daily_bid_reminders", now - timedelta(hours=2))
    _set_last_run("daily_insurance_expiration", now - timedelta(hours=2))
    _set_last_run("post_deadline_escalation", now - timedelta(hours=2))


def _run(db, notification_creator=None) -> dict:
    return asyncio.run(
        run_daily_scheduler_self_check(
            db,
            notification_creator=notification_creator
            or MagicMock(return_value={"id": "n"}),
        )
    )


@pytest.fixture(autouse=True)
def _reset_scheduler_state():
    """Wipe ``_last_run`` and ``_started_at`` around every test."""
    scheduler_module._last_run.clear()
    scheduler_module._started_at = None
    yield
    scheduler_module._last_run.clear()
    scheduler_module._started_at = None


# ── Tests ────────────────────────────────────────────────────────────────


class TestRunDailySchedulerSelfCheck:
    def test_no_stale_jobs_returns_empty(self):
        now = datetime.now(timezone.utc)
        _seed_fresh(now)
        scheduler_module._started_at = now - timedelta(days=7)
        db = FakeDB(users=[_admin()])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["stale_jobs"] == []
        assert result["admins_notified"] == 0
        assert result["deduplicated_skipped"] == 0
        mock.assert_not_called()

    def test_one_daily_job_stale_notifies_admins(self):
        now = datetime.now(timezone.utc)
        _seed_fresh(now)
        stale_at = now - timedelta(hours=30)
        _set_last_run("daily_bid_reminders", stale_at)
        scheduler_module._started_at = now - timedelta(days=7)

        admins = [_admin(name="Alice"), _admin(name="Bob")]
        db = FakeDB(users=admins)
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["stale_jobs"] == ["daily_bid_reminders"]
        assert result["admins_notified"] == 2
        assert mock.call_count == 2
        kw = mock.call_args.kwargs
        assert "expected every 1 day" in kw["message"]
        assert stale_at.isoformat() in kw["message"]
        assert kw["notification_type"] == "scheduler_alert"
        assert kw["reference_type"] is None
        assert kw["reference_id"] is None
        assert kw["dedupe"] is False

    def test_hourly_job_stale_uses_correct_interval(self):
        now = datetime.now(timezone.utc)
        _seed_fresh(now)
        _set_last_run("revision_expiry", now - timedelta(hours=4))
        scheduler_module._started_at = now - timedelta(days=7)

        db = FakeDB(users=[_admin()])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["stale_jobs"] == ["revision_expiry"]
        assert "expected every 1 hour" in mock.call_args.kwargs["message"]

    def test_hourly_job_within_grace_not_stale(self):
        now = datetime.now(timezone.utc)
        _seed_fresh(now)
        _set_last_run("revision_expiry", now - timedelta(hours=2))
        scheduler_module._started_at = now - timedelta(days=7)

        db = FakeDB(users=[_admin()])
        result = _run(db)

        assert result["stale_jobs"] == []

    def test_daily_job_within_grace_not_stale(self):
        now = datetime.now(timezone.utc)
        _seed_fresh(now)
        _set_last_run("daily_bid_reminders", now - timedelta(hours=25))
        scheduler_module._started_at = now - timedelta(days=7)

        db = FakeDB(users=[_admin()])
        result = _run(db)

        assert result["stale_jobs"] == []

    def test_cold_start_grace_skips_never_run_jobs(self):
        # Nothing in _last_run for any job; scheduler started 30 minutes ago.
        scheduler_module._started_at = datetime.now(timezone.utc) - timedelta(minutes=30)

        db = FakeDB(users=[_admin()])
        result = _run(db)

        assert result["stale_jobs"] == []

    def test_cold_start_expired_grace_flags_never_run_jobs(self):
        now = datetime.now(timezone.utc)
        # All four jobs absent from _last_run, but scheduler has been up for days.
        scheduler_module._started_at = now - timedelta(days=3)

        db = FakeDB(users=[_admin()])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert set(result["stale_jobs"]) == set(
            ["revision_expiry", "daily_bid_reminders", "daily_insurance_expiration", "post_deadline_escalation"]
        )
        msg = mock.call_args.kwargs["message"]
        assert "daily_bid_reminders: expected every 1 day, last ran never" in msg

    def test_self_check_excludes_itself(self):
        now = datetime.now(timezone.utc)
        _seed_fresh(now)
        # Even with a stale self-check entry, it must not appear in stale_jobs.
        _set_last_run("scheduler_self_check", now - timedelta(days=30))
        scheduler_module._started_at = now - timedelta(days=7)

        db = FakeDB(users=[_admin()])
        result = _run(db)

        assert result["stale_jobs"] == []

    def test_multiple_stale_jobs_one_notification_per_admin(self):
        now = datetime.now(timezone.utc)
        _seed_fresh(now)
        _set_last_run("daily_bid_reminders", now - timedelta(hours=30))
        _set_last_run("revision_expiry", now - timedelta(hours=4))
        scheduler_module._started_at = now - timedelta(days=7)

        admins = [_admin(name=f"A{i}") for i in range(3)]
        db = FakeDB(users=admins)
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert set(result["stale_jobs"]) == {"daily_bid_reminders", "revision_expiry"}
        assert result["admins_notified"] == 3
        assert mock.call_count == 3
        for call in mock.call_args_list:
            msg = call.kwargs["message"]
            assert "daily_bid_reminders" in msg
            assert "revision_expiry" in msg

    def test_title_singular_vs_plural(self):
        now = datetime.now(timezone.utc)
        scheduler_module._started_at = now - timedelta(days=7)
        admin = _admin()

        # One stale.
        _seed_fresh(now)
        _set_last_run("daily_bid_reminders", now - timedelta(hours=30))
        db = FakeDB(users=[admin])
        mock = MagicMock(return_value={"id": "n"})
        _run(db, notification_creator=mock)
        assert mock.call_args.kwargs["title"] == "Scheduler alert: 1 job stale"

        # Two stale.
        scheduler_module._last_run.clear()
        _seed_fresh(now)
        _set_last_run("daily_bid_reminders", now - timedelta(hours=30))
        _set_last_run("revision_expiry", now - timedelta(hours=4))
        db = FakeDB(users=[admin])
        mock = MagicMock(return_value={"id": "n"})
        _run(db, notification_creator=mock)
        assert mock.call_args.kwargs["title"] == "Scheduler alert: 2 jobs stale"

    def test_dedupe_skips_admins_with_unread_scheduler_alert(self):
        now = datetime.now(timezone.utc)
        _seed_fresh(now)
        _set_last_run("daily_bid_reminders", now - timedelta(hours=30))
        scheduler_module._started_at = now - timedelta(days=7)

        a, b, c = _admin(name="A"), _admin(name="B"), _admin(name="C")
        existing = {
            "id": str(uuid4()),
            "user_id": a["id"],
            "notification_type": "scheduler_alert",
            "reference_type": None,
            "reference_id": None,
            "is_read": False,
        }
        db = FakeDB(users=[a, b, c], notifications=[existing])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["deduplicated_skipped"] == 1
        assert result["admins_notified"] == 2
        notified_ids = {call.kwargs["user_id"] for call in mock.call_args_list}
        assert a["id"] not in notified_ids
        assert {b["id"], c["id"]} == notified_ids

    def test_no_active_admins_returns_zero_notified(self):
        now = datetime.now(timezone.utc)
        _seed_fresh(now)
        _set_last_run("daily_bid_reminders", now - timedelta(hours=30))
        scheduler_module._started_at = now - timedelta(days=7)

        db = FakeDB(users=[])  # No admins.
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["stale_jobs"] == ["daily_bid_reminders"]
        assert result["admins_notified"] == 0
        assert result["deduplicated_skipped"] == 0
        mock.assert_not_called()

    def test_partial_admin_failure_isolated(self):
        now = datetime.now(timezone.utc)
        _seed_fresh(now)
        _set_last_run("daily_bid_reminders", now - timedelta(hours=30))
        scheduler_module._started_at = now - timedelta(days=7)

        admins = [_admin(name=f"A{i}") for i in range(3)]
        db = FakeDB(users=admins)

        calls = {"n": 0}

        def flaky(*_a, **_kw):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("simulated supabase failure")
            return {"id": "n"}

        mock = MagicMock(side_effect=flaky)
        result = _run(db, notification_creator=mock)

        assert mock.call_count == 3
        assert result["admins_notified"] == 2
        assert result["deduplicated_skipped"] == 0

    def test_payload_shape(self):
        now = datetime.now(timezone.utc)
        _seed_fresh(now)
        scheduler_module._started_at = now - timedelta(days=7)

        db = FakeDB(users=[_admin()])
        result = _run(db)

        assert set(result.keys()) == {
            "stale_jobs",
            "admins_notified",
            "deduplicated_skipped",
            "duration_seconds",
        }
        assert isinstance(result["stale_jobs"], list)
        assert isinstance(result["admins_notified"], int)
        assert isinstance(result["deduplicated_skipped"], int)
        assert isinstance(result["duration_seconds"], float)
