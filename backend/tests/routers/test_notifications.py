"""Integration tests for /api/v1/notifications endpoints.

Overrides `get_supabase` with a notifications-aware fake and
`get_current_active_user` with a deterministic admin profile. The fake
honors `.eq("user_id", ...)` filtering so RLS-equivalent isolation can be
verified end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app


USER_A_ID = str(uuid4())
USER_B_ID = str(uuid4())

USER_A = {
    "user_id": USER_A_ID,
    "email": "a@example.com",
    "full_name": "User A",
    "role": "admin",
    "is_active": True,
}


def _make_row(
    *,
    user_id: str,
    notification_type: str = "scheduler_alert",
    title: str = "test",
    is_read: bool = False,
    reference_type: str | None = None,
    reference_id: str | None = None,
    created_at: datetime | None = None,
) -> dict:
    return {
        "id": str(uuid4()),
        "user_id": user_id,
        "title": title,
        "message": "msg",
        "notification_type": notification_type,
        "reference_type": reference_type,
        "reference_id": reference_id,
        "is_read": is_read,
        "created_at": (created_at or datetime.now(timezone.utc)).isoformat(),
    }


# ── Fake DB ──────────────────────────────────────────────────────────────


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, fake, table):
        self._fake = fake
        self._table = table
        self._op = "select"
        self._payload = None
        self._filters: list[tuple] = []
        self._limit = None
        self._range: tuple | None = None
        self._order: tuple | None = None
        self._want_count = False

    def select(self, *_a, count=None, **_k):
        self._op = "select"
        if count == "exact":
            self._want_count = True
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

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, lo, hi):
        self._range = (lo, hi)
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
    return True


class FakeDB:
    def __init__(self, notifications=None, packages=None):
        self.notifications: list[dict] = notifications or []
        self.packages: list[dict] = packages or []

    def table(self, name):
        return _Query(self, name)

    def _resolve(self, q: _Query):
        if q._table == "notifications" and q._op == "select":
            rows = [r for r in self.notifications if _matches(r, q._filters)]
            if q._order is not None:
                col, desc = q._order
                rows = sorted(rows, key=lambda r: r.get(col) or "", reverse=desc)
            if q._range is not None:
                lo, hi = q._range
                rows = rows[lo : hi + 1]
            elif q._limit is not None:
                rows = rows[: q._limit]
            count = len(
                [r for r in self.notifications if _matches(r, q._filters)]
            ) if q._want_count else None
            return _Result(rows, count=count)

        if q._table == "notifications" and q._op == "update":
            updated = []
            for r in self.notifications:
                if _matches(r, q._filters):
                    r.update(q._payload)
                    updated.append(r)
            return _Result(updated)

        if q._table == "bid_packages" and q._op == "select":
            rows = [p for p in self.packages if _matches(p, q._filters)]
            if q._limit is not None:
                rows = rows[: q._limit]
            return _Result(rows)

        return _Result([])


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def fake_db():
    return FakeDB()


@pytest.fixture()
def client(fake_db):
    app.dependency_overrides[get_current_active_user] = lambda: USER_A
    app.dependency_overrides[get_supabase] = lambda: fake_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── GET /notifications ───────────────────────────────────────────────────


class TestListNotifications:
    def test_returns_only_current_users_rows(self, client, fake_db):
        fake_db.notifications = [
            _make_row(user_id=USER_A_ID, title="mine"),
            _make_row(user_id=USER_B_ID, title="not mine"),
        ]
        resp = client.get("/api/v1/notifications")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["title"] == "mine"

    def test_unread_only_filter(self, client, fake_db):
        fake_db.notifications = [
            _make_row(user_id=USER_A_ID, title="unread", is_read=False),
            _make_row(user_id=USER_A_ID, title="read", is_read=True),
        ]
        all_resp = client.get("/api/v1/notifications").json()
        unread_resp = client.get(
            "/api/v1/notifications", params={"unread_only": "true"}
        ).json()
        assert len(all_resp) == 2
        assert len(unread_resp) == 1
        assert unread_resp[0]["title"] == "unread"

    def test_newest_first_ordering(self, client, fake_db):
        old = datetime.now(timezone.utc) - timedelta(days=2)
        new = datetime.now(timezone.utc)
        fake_db.notifications = [
            _make_row(user_id=USER_A_ID, title="old", created_at=old),
            _make_row(user_id=USER_A_ID, title="new", created_at=new),
        ]
        rows = client.get("/api/v1/notifications").json()
        assert rows[0]["title"] == "new"

    def test_pagination_limit_clamped_upper(self, client, fake_db):
        fake_db.notifications = [
            _make_row(user_id=USER_A_ID, title=f"row-{i}") for i in range(5)
        ]
        # FastAPI Query(le=100) rejects 1000 with 422
        resp = client.get("/api/v1/notifications", params={"limit": 1000})
        assert resp.status_code == 422

    def test_pagination_limit_clamped_lower(self, client):
        resp = client.get("/api/v1/notifications", params={"limit": 0})
        assert resp.status_code == 422

    def test_pagination_offset(self, client, fake_db):
        # Build 5 rows in creation order; newest first will reverse them.
        base = datetime.now(timezone.utc)
        fake_db.notifications = [
            _make_row(
                user_id=USER_A_ID,
                title=f"row-{i}",
                created_at=base + timedelta(seconds=i),
            )
            for i in range(5)
        ]
        page1 = client.get(
            "/api/v1/notifications", params={"limit": 2, "offset": 0}
        ).json()
        page2 = client.get(
            "/api/v1/notifications", params={"limit": 2, "offset": 2}
        ).json()
        assert [r["title"] for r in page1] == ["row-4", "row-3"]
        assert [r["title"] for r in page2] == ["row-2", "row-1"]

    def test_deep_link_path_for_vendors(self, client, fake_db):
        vendor_id = str(uuid4())
        fake_db.notifications = [
            _make_row(
                user_id=USER_A_ID,
                notification_type="insurance_expired",
                reference_type="vendors",
                reference_id=vendor_id,
            )
        ]
        rows = client.get("/api/v1/notifications").json()
        assert rows[0]["deep_link_path"] == f"/vendors/{vendor_id}"

    def test_deep_link_path_null_for_scheduler_alert(self, client, fake_db):
        fake_db.notifications = [
            _make_row(
                user_id=USER_A_ID,
                notification_type="scheduler_alert",
                reference_type=None,
                reference_id=None,
            )
        ]
        rows = client.get("/api/v1/notifications").json()
        assert rows[0]["deep_link_path"] is None

    def test_deep_link_path_for_bid_packages(self, client, fake_db):
        pkg_id = str(uuid4())
        task_id = str(uuid4())
        project_id = str(uuid4())
        fake_db.notifications = [
            _make_row(
                user_id=USER_A_ID,
                notification_type="post_deadline_non_responders",
                reference_type="bid_packages",
                reference_id=pkg_id,
            )
        ]
        fake_db.packages = [
            {
                "id": pkg_id,
                "task_id": task_id,
                "tasks": {"id": task_id, "project_id": project_id},
            }
        ]
        rows = client.get("/api/v1/notifications").json()
        assert (
            rows[0]["deep_link_path"]
            == f"/projects/{project_id}/tasks/{task_id}/bid-packages/{pkg_id}"
        )


# ── GET /notifications/unread-count ──────────────────────────────────────


class TestUnreadCount:
    def test_counts_only_current_user_unread(self, client, fake_db):
        fake_db.notifications = [
            _make_row(user_id=USER_A_ID, is_read=False),
            _make_row(user_id=USER_A_ID, is_read=False),
            _make_row(user_id=USER_A_ID, is_read=True),
            _make_row(user_id=USER_B_ID, is_read=False),  # not mine
        ]
        resp = client.get("/api/v1/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json() == {"count": 2}

    def test_returns_zero_when_no_unread(self, client, fake_db):
        fake_db.notifications = [_make_row(user_id=USER_A_ID, is_read=True)]
        assert client.get("/api/v1/notifications/unread-count").json() == {
            "count": 0
        }


# ── PATCH /notifications/{id}/read ───────────────────────────────────────


class TestMarkRead:
    def test_marks_own_notification_read(self, client, fake_db):
        row = _make_row(user_id=USER_A_ID, is_read=False)
        fake_db.notifications = [row]

        resp = client.patch(f"/api/v1/notifications/{row['id']}/read")
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True
        # DB row was actually mutated
        assert fake_db.notifications[0]["is_read"] is True

    def test_other_users_notification_returns_404(self, client, fake_db):
        other_row = _make_row(user_id=USER_B_ID, is_read=False)
        fake_db.notifications = [other_row]
        resp = client.patch(f"/api/v1/notifications/{other_row['id']}/read")
        assert resp.status_code == 404
        # other user's row untouched
        assert fake_db.notifications[0]["is_read"] is False

    def test_nonexistent_id_returns_404(self, client):
        resp = client.patch(f"/api/v1/notifications/{uuid4()}/read")
        assert resp.status_code == 404


# ── PATCH /notifications/mark-all-read ───────────────────────────────────


class TestMarkAllRead:
    def test_returns_updated_count_and_mutates(self, client, fake_db):
        fake_db.notifications = [
            _make_row(user_id=USER_A_ID, is_read=False),
            _make_row(user_id=USER_A_ID, is_read=False),
            _make_row(user_id=USER_A_ID, is_read=True),  # already read
            _make_row(user_id=USER_B_ID, is_read=False),  # not mine
        ]
        resp = client.patch("/api/v1/notifications/mark-all-read")
        assert resp.status_code == 200
        assert resp.json() == {"updated_count": 2}
        # only user A's unread rows were touched
        a_rows = [r for r in fake_db.notifications if r["user_id"] == USER_A_ID]
        assert all(r["is_read"] for r in a_rows)
        # user B's row untouched
        b_row = next(r for r in fake_db.notifications if r["user_id"] == USER_B_ID)
        assert b_row["is_read"] is False

    def test_no_unread_returns_zero(self, client, fake_db):
        fake_db.notifications = [_make_row(user_id=USER_A_ID, is_read=True)]
        resp = client.patch("/api/v1/notifications/mark-all-read")
        assert resp.json() == {"updated_count": 0}
