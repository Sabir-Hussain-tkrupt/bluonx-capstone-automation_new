"""Unit tests for NotificationService.

Uses a small purpose-built FakeSupabase double — minimal but covers every
chain the service touches (select/insert with .eq, .is_, .limit).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.notification_service import (
    NOTIFICATION_TYPES,
    build_notification_deep_link,
    create_notification,
    create_notifications_bulk,
)


# ── Fake supabase tailored to the service's chains ───────────────────────


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, fake: "FakeNotificationsDB", table: str):
        self._fake = fake
        self._table = table
        self._op = "select"
        self._payload = None
        self._filters: list[tuple] = []  # (kind, col, val)
        self._limit = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        return self._fake._resolve(
            self._table, self._op, self._filters, self._payload, self._limit
        )


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
    return True


class FakeNotificationsDB:
    """Notifications-table-aware fake. Also serves bid_packages reads for
    the deep-link builder. Records inserts so tests can assert on them."""

    def __init__(self, rows=None, packages=None):
        self.rows: list[dict] = rows or []
        self.packages: list[dict] = packages or []
        self.inserts: list[dict] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def _resolve(self, table, op, filters, payload, limit):
        if table == "notifications" and op == "select":
            matched = [r for r in self.rows if _matches(r, filters)]
            if limit:
                matched = matched[:limit]
            return _Result(matched)

        if table == "notifications" and op == "insert":
            row = dict(payload)
            row.setdefault("id", str(uuid4()))
            row.setdefault("created_at", "2026-05-24T00:00:00Z")
            self.rows.append(row)
            self.inserts.append(row)
            return _Result([row])

        if table == "bid_packages" and op == "select":
            matched = [p for p in self.packages if _matches(p, filters)]
            if limit:
                matched = matched[:limit]
            return _Result(matched)

        return _Result([])


# ── create_notification ──────────────────────────────────────────────────


class TestCreateNotification:
    def test_inserts_new_row_when_no_duplicate(self):
        db = FakeNotificationsDB()
        user_id = uuid4()
        vendor_id = uuid4()

        row = create_notification(
            db,
            user_id=user_id,
            notification_type="insurance_expiring",
            title="Insurance expiring",
            message="ABC Excavation expires in 7 days",
            reference_type="vendors",
            reference_id=vendor_id,
        )

        assert len(db.inserts) == 1
        assert row["user_id"] == str(user_id)
        assert row["notification_type"] == "insurance_expiring"
        assert row["reference_id"] == str(vendor_id)
        assert row["is_read"] is False

    def test_rejects_unknown_notification_type(self):
        db = FakeNotificationsDB()
        with pytest.raises(ValueError, match="Unknown notification_type"):
            create_notification(
                db,
                user_id=uuid4(),
                notification_type="not_a_real_type",
                title="x",
            )
        assert db.inserts == []

    def test_dedupe_returns_existing_unread_row(self):
        user_id = str(uuid4())
        vendor_id = str(uuid4())
        existing = {
            "id": str(uuid4()),
            "user_id": user_id,
            "notification_type": "insurance_expired",
            "reference_type": "vendors",
            "reference_id": vendor_id,
            "is_read": False,
            "title": "old title",
            "message": "old message",
            "created_at": "2026-05-20T00:00:00Z",
        }
        db = FakeNotificationsDB(rows=[existing])

        row = create_notification(
            db,
            user_id=user_id,
            notification_type="insurance_expired",
            title="new title",
            reference_type="vendors",
            reference_id=vendor_id,
        )

        assert row["id"] == existing["id"]
        assert row["title"] == "old title"  # unchanged — not re-inserted
        assert db.inserts == []  # no insert recorded

    def test_dedupe_does_not_match_read_rows(self):
        """If the same triple exists but is_read=TRUE, a new row is created."""
        user_id = str(uuid4())
        vendor_id = str(uuid4())
        read_row = {
            "id": str(uuid4()),
            "user_id": user_id,
            "notification_type": "insurance_expired",
            "reference_type": "vendors",
            "reference_id": vendor_id,
            "is_read": True,
        }
        db = FakeNotificationsDB(rows=[read_row])

        row = create_notification(
            db,
            user_id=user_id,
            notification_type="insurance_expired",
            title="new",
            reference_type="vendors",
            reference_id=vendor_id,
        )

        assert len(db.inserts) == 1
        assert row["id"] != read_row["id"]

    def test_dedupe_null_reference_id_matches_null(self):
        user_id = str(uuid4())
        existing = {
            "id": str(uuid4()),
            "user_id": user_id,
            "notification_type": "scheduler_alert",
            "reference_type": None,
            "reference_id": None,
            "is_read": False,
        }
        db = FakeNotificationsDB(rows=[existing])

        row = create_notification(
            db,
            user_id=user_id,
            notification_type="scheduler_alert",
            title="alert",
        )

        assert row["id"] == existing["id"]
        assert db.inserts == []

    def test_dedupe_disabled_always_inserts(self):
        user_id = str(uuid4())
        vendor_id = str(uuid4())
        existing = {
            "id": str(uuid4()),
            "user_id": user_id,
            "notification_type": "insurance_expired",
            "reference_type": "vendors",
            "reference_id": vendor_id,
            "is_read": False,
        }
        db = FakeNotificationsDB(rows=[existing])

        row = create_notification(
            db,
            user_id=user_id,
            notification_type="insurance_expired",
            title="forced",
            reference_type="vendors",
            reference_id=vendor_id,
            dedupe=False,
        )

        assert len(db.inserts) == 1
        assert row["id"] != existing["id"]


# ── create_notifications_bulk ────────────────────────────────────────────


class TestCreateNotificationsBulk:
    def test_loops_and_dedupes_per_item(self):
        user_a = str(uuid4())
        user_b = str(uuid4())
        vendor_id = str(uuid4())
        existing = {
            "id": str(uuid4()),
            "user_id": user_a,
            "notification_type": "insurance_expired",
            "reference_type": "vendors",
            "reference_id": vendor_id,
            "is_read": False,
        }
        db = FakeNotificationsDB(rows=[existing])

        out = create_notifications_bulk(
            db,
            notifications=[
                {
                    "user_id": user_a,
                    "notification_type": "insurance_expired",
                    "title": "x",
                    "reference_type": "vendors",
                    "reference_id": vendor_id,
                },
                {
                    "user_id": user_b,
                    "notification_type": "insurance_expired",
                    "title": "x",
                    "reference_type": "vendors",
                    "reference_id": vendor_id,
                },
            ],
        )

        assert len(out) == 2
        assert out[0]["id"] == existing["id"]  # deduped
        assert out[1]["user_id"] == user_b  # newly inserted
        assert len(db.inserts) == 1  # only user_b row inserted


# ── build_notification_deep_link ─────────────────────────────────────────


class TestBuildDeepLink:
    def test_vendors(self):
        vendor_id = uuid4()
        link = build_notification_deep_link(
            {"reference_type": "vendors", "reference_id": str(vendor_id)},
            FakeNotificationsDB(),
        )
        assert link == f"/vendors/{vendor_id}"

    def test_bid_packages_resolves_full_path(self):
        bid_pkg_id = str(uuid4())
        task_id = str(uuid4())
        project_id = str(uuid4())
        db = FakeNotificationsDB(
            packages=[
                {
                    "id": bid_pkg_id,
                    "task_id": task_id,
                    "tasks": {"id": task_id, "project_id": project_id},
                }
            ]
        )
        link = build_notification_deep_link(
            {"reference_type": "bid_packages", "reference_id": bid_pkg_id}, db
        )
        assert link == f"/projects/{project_id}/tasks/{task_id}/bid-packages/{bid_pkg_id}"

    def test_bid_packages_missing_row_returns_none(self):
        db = FakeNotificationsDB()  # no packages
        link = build_notification_deep_link(
            {"reference_type": "bid_packages", "reference_id": str(uuid4())}, db
        )
        assert link is None

    def test_null_reference_returns_none(self):
        link = build_notification_deep_link(
            {"reference_type": None, "reference_id": None}, FakeNotificationsDB()
        )
        assert link is None

    def test_unknown_reference_type_returns_none(self):
        link = build_notification_deep_link(
            {"reference_type": "users", "reference_id": str(uuid4())},
            FakeNotificationsDB(),
        )
        assert link is None


def test_controlled_vocabulary_matches_spec():
    """Catch accidental additions/removals of notification types."""
    assert NOTIFICATION_TYPES == frozenset({
        "insurance_expiring",
        "insurance_expired",
        "post_deadline_non_responders",
        "scheduler_alert",
    })
