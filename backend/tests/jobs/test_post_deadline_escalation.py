"""Tests for the post_deadline_escalation job (Task 7.6).

Calls the inner `run_daily_post_deadline_escalation` directly so the
@tracked_job decorator is bypassed and counts can be asserted without
mucking with scheduler state. `create_notification` is injected as a
MagicMock so we can both observe call kwargs and induce failures.

The fake DB is self-contained here (mirroring test_insurance_expiration.py)
rather than extending conftest.py — this job's chain set (embedded select,
bulk UPDATE with .in_(), notifications dedupe SELECT) is specific enough
that a per-test fake keeps the shared conftest from accreting one-off
methods.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.jobs.post_deadline_escalation import run_daily_post_deadline_escalation


# ── Fake Supabase ───────────────────────────────────────────────────────


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

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def lt(self, col, val):
        self._filters.append(("lt", col, val))
        return self

    def gte(self, col, val):
        self._filters.append(("gte", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
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
        if kind == "lt" and (actual is None or actual >= val):
            return False
        if kind == "gte" and (actual is None or actual < val):
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
        bid_packages: list[dict] | None = None,
        bid_invitations: list[dict] | None = None,
        users: list[dict] | None = None,
        notifications: list[dict] | None = None,
    ):
        self.bid_packages = bid_packages or []
        self.bid_invitations = bid_invitations or []
        self.users = users or []
        self.notifications = notifications or []
        # Observed UPDATE ops on bid_invitations: (bid_package_id, payload, n_flipped)
        self.invitation_updates: list[tuple] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def _resolve(self, q: _Query):
        if q._op == "select":
            if q._table == "bid_packages":
                return _Result([r for r in self.bid_packages if _matches(r, q._filters)])
            if q._table == "bid_invitations":
                return _Result(
                    [r for r in self.bid_invitations if _matches(r, q._filters)]
                )
            if q._table == "users":
                return _Result([r for r in self.users if _matches(r, q._filters)])
            if q._table == "notifications":
                return _Result(
                    [r for r in self.notifications if _matches(r, q._filters)]
                )
            return _Result([])

        if q._op == "update" and q._table == "bid_invitations":
            matched = [r for r in self.bid_invitations if _matches(r, q._filters)]
            for r in matched:
                r.update(q._payload)
            pkg_id = next(
                (v for k, c, v in q._filters if k == "eq" and c == "bid_package_id"),
                None,
            )
            self.invitation_updates.append((pkg_id, dict(q._payload), len(matched)))
            return _Result(list(matched))

        return _Result([])


# ── Fixture helpers ─────────────────────────────────────────────────────


def _in_window() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()


def _outside_window() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()


def _pkg(
    pkg_id: str,
    *,
    created_by: str,
    deadline: str,
    project_name: str = "Project",
    task_name: str = "Task",
    project_id: str = "proj-1",
) -> dict:
    return {
        "id": pkg_id,
        "deadline": deadline,
        "created_by": created_by,
        "tasks": {
            "name": task_name,
            "project_id": project_id,
            "projects": {"name": project_name},
        },
    }


def _inv(
    inv_id: str,
    *,
    pkg_id: str,
    status: str,
    company: str = "Vendor Co.",
    contact_name: str = "Pat Contact",
    email: str = "pat@example.com",
) -> dict:
    return {
        "id": inv_id,
        "bid_package_id": pkg_id,
        "vendor_id": f"v-{inv_id}",
        "vendor_contact_id": f"c-{inv_id}",
        "status": status,
        "vendors": {"company_name": company},
        "vendor_contacts": {"full_name": contact_name, "email": email},
    }


def _user(uid: str, *, active: bool = True, deleted: bool = False) -> dict:
    return {
        "id": uid,
        "email": f"{uid}@example.com",
        "full_name": "Owner",
        "is_active": active,
        "deleted_at": "2026-01-01T00:00:00+00:00" if deleted else None,
    }


def _run(db: FakeDB, notification_creator=None) -> dict:
    return asyncio.run(
        run_daily_post_deadline_escalation(
            db,
            notification_creator=notification_creator
            or MagicMock(return_value={"id": "n"}),
        )
    )


# ── Tests ───────────────────────────────────────────────────────────────


class TestRunDailyPostDeadlineEscalation:
    # 1
    def test_no_packages_in_window_returns_zeros(self):
        db = FakeDB()
        result = _run(db)
        assert result["packages_affected"] == 0
        assert result["notifications_created"] == 0
        assert result["invitations_marked_no_response"] == 0
        assert result["deduplicated_skipped"] == 0
        assert result["skipped_inactive_creator"] == 0
        assert "duration_seconds" in result

    # 2
    def test_package_with_only_submitted_vendors_excluded(self):
        creator = _user("u1")
        pkg = _pkg("p1", created_by="u1", deadline=_in_window())
        invs = [
            _inv("i1", pkg_id="p1", status="submitted", company="A"),
            _inv("i2", pkg_id="p1", status="declined", company="B"),
        ]
        db = FakeDB(bid_packages=[pkg], bid_invitations=invs, users=[creator])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["packages_affected"] == 0
        assert result["notifications_created"] == 0
        assert result["invitations_marked_no_response"] == 0
        mock.assert_not_called()
        assert db.invitation_updates == []

    # 3
    def test_package_with_non_responders_creates_notification(self):
        creator = _user("u1")
        pkg = _pkg(
            "p1",
            created_by="u1",
            deadline=_in_window(),
            project_name="Sunset Hills",
            task_name="Excavation",
        )
        invs = [
            _inv(
                "i1",
                pkg_id="p1",
                status="sent",
                company="Acme",
                contact_name="Alice",
                email="a@a.com",
            ),
            _inv(
                "i2",
                pkg_id="p1",
                status="opened",
                company="Beta",
                contact_name="Bob",
                email="b@b.com",
            ),
        ]
        db = FakeDB(bid_packages=[pkg], bid_invitations=invs, users=[creator])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["packages_affected"] == 1
        assert result["notifications_created"] == 1
        assert result["invitations_marked_no_response"] == 2

        kw = mock.call_args.kwargs
        assert kw["notification_type"] == "post_deadline_non_responders"
        assert kw["reference_type"] == "bid_packages"
        assert kw["reference_id"] == "p1"
        assert kw["user_id"] == "u1"
        assert kw["dedupe"] is False
        assert "Sunset Hills" in kw["title"]
        assert "Excavation" in kw["title"]
        assert "Acme" in kw["message"]
        assert "Beta" in kw["message"]
        # Both invitations flipped in place:
        assert all(i["status"] == "no_response" for i in invs)

    # 4
    def test_title_uses_correct_count(self):
        creator = _user("u1")
        pkg = _pkg("p1", created_by="u1", deadline=_in_window())
        invs = [
            _inv(f"i{i}", pkg_id="p1", status="sent", company=f"Co{i}")
            for i in range(5)
        ]
        db = FakeDB(bid_packages=[pkg], bid_invitations=invs, users=[creator])
        mock = MagicMock(return_value={"id": "n"})

        _run(db, notification_creator=mock)

        assert mock.call_args.kwargs["title"].startswith("5 vendors did not respond")

    # 5
    def test_message_truncates_at_5_with_overflow(self):
        creator = _user("u1")
        pkg = _pkg("p1", created_by="u1", deadline=_in_window())
        invs = [
            _inv(f"i{i}", pkg_id="p1", status="sent", company=f"Co{i}")
            for i in range(7)
        ]
        db = FakeDB(bid_packages=[pkg], bid_invitations=invs, users=[creator])
        mock = MagicMock(return_value={"id": "n"})

        _run(db, notification_creator=mock)

        message = mock.call_args.kwargs["message"]
        lines = message.split("\n")
        # 5 vendor lines + 1 overflow line.
        assert len(lines) == 6
        assert lines[-1] == "...and 2 more."
        # The first 5 vendors are present by company name.
        for i in range(5):
            assert any(f"Co{i}" in line for line in lines[:5])

    # 6
    def test_dedupe_skips_existing_unread(self):
        creator = _user("u1")
        pkg = _pkg("p1", created_by="u1", deadline=_in_window())
        invs = [_inv("i1", pkg_id="p1", status="sent", company="A")]
        existing = {
            "id": "n-existing",
            "user_id": "u1",
            "notification_type": "post_deadline_non_responders",
            "reference_type": "bid_packages",
            "reference_id": "p1",
            "is_read": False,
        }
        db = FakeDB(
            bid_packages=[pkg],
            bid_invitations=invs,
            users=[creator],
            notifications=[existing],
        )
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["deduplicated_skipped"] == 1
        assert result["notifications_created"] == 0
        assert result["invitations_marked_no_response"] == 0
        assert db.invitation_updates == []
        mock.assert_not_called()
        # Invitation remained at its original status.
        assert invs[0]["status"] == "sent"

    # 7
    def test_inactive_creator_skipped(self):
        creator = _user("u1", active=False)
        pkg = _pkg("p1", created_by="u1", deadline=_in_window())
        invs = [_inv("i1", pkg_id="p1", status="sent", company="A")]
        db = FakeDB(bid_packages=[pkg], bid_invitations=invs, users=[creator])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["skipped_inactive_creator"] == 1
        assert result["notifications_created"] == 0
        assert result["invitations_marked_no_response"] == 0
        mock.assert_not_called()
        assert invs[0]["status"] == "sent"

    # 8
    def test_deleted_creator_skipped(self):
        creator = _user("u1", deleted=True)
        pkg = _pkg("p1", created_by="u1", deadline=_in_window())
        invs = [_inv("i1", pkg_id="p1", status="sent", company="A")]
        db = FakeDB(bid_packages=[pkg], bid_invitations=invs, users=[creator])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["skipped_inactive_creator"] == 1
        assert result["notifications_created"] == 0
        mock.assert_not_called()
        assert invs[0]["status"] == "sent"

    # 9
    def test_invitations_marked_no_response_only_after_successful_dispatch(self):
        creator = _user("u1")
        pkg = _pkg("p1", created_by="u1", deadline=_in_window())
        invs = [_inv("i1", pkg_id="p1", status="sent", company="A")]
        db = FakeDB(bid_packages=[pkg], bid_invitations=invs, users=[creator])
        mock = MagicMock(side_effect=RuntimeError("boom"))

        result = _run(db, notification_creator=mock)

        assert result["notifications_created"] == 0
        assert result["invitations_marked_no_response"] == 0
        assert db.invitation_updates == []
        assert invs[0]["status"] == "sent"
        # Worker still completed cleanly.
        assert "duration_seconds" in result

    # 10
    def test_multiple_packages_one_creator(self):
        creator = _user("u1")
        pkg_a = _pkg(
            "p1",
            created_by="u1",
            deadline=_in_window(),
            project_name="Alpha",
            task_name="TA",
        )
        pkg_b = _pkg(
            "p2",
            created_by="u1",
            deadline=_in_window(),
            project_name="Beta",
            task_name="TB",
        )
        invs = [
            _inv("i1", pkg_id="p1", status="sent", company="A1"),
            _inv("i2", pkg_id="p2", status="sent", company="B1"),
        ]
        db = FakeDB(
            bid_packages=[pkg_a, pkg_b], bid_invitations=invs, users=[creator]
        )
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["packages_affected"] == 2
        assert result["notifications_created"] == 2
        assert mock.call_count == 2
        refs = {c.kwargs["reference_id"] for c in mock.call_args_list}
        assert refs == {"p1", "p2"}
        user_ids = {c.kwargs["user_id"] for c in mock.call_args_list}
        assert user_ids == {"u1"}

    # 11
    def test_partial_admin_failure_still_flips_invitations(self):
        creator = _user("u1")
        pkg = _pkg("p1", created_by="u1", deadline=_in_window())
        invs = [
            _inv("i1", pkg_id="p1", status="sent", company="A"),
            _inv("i2", pkg_id="p1", status="opened", company="B"),
        ]
        db = FakeDB(bid_packages=[pkg], bid_invitations=invs, users=[creator])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["notifications_created"] == 1
        assert result["invitations_marked_no_response"] == 2
        assert all(i["status"] == "no_response" for i in invs)

    # 12
    def test_payload_shape(self):
        db = FakeDB()
        result = _run(db)

        assert set(result.keys()) == {
            "packages_affected",
            "notifications_created",
            "invitations_marked_no_response",
            "deduplicated_skipped",
            "skipped_inactive_creator",
            "duration_seconds",
        }
        assert isinstance(result["packages_affected"], int)
        assert isinstance(result["notifications_created"], int)
        assert isinstance(result["invitations_marked_no_response"], int)
        assert isinstance(result["deduplicated_skipped"], int)
        assert isinstance(result["skipped_inactive_creator"], int)
        assert isinstance(result["duration_seconds"], float)

    # Bonus: confirm out-of-window deadlines are excluded by the query.
    def test_outside_window_package_excluded(self):
        creator = _user("u1")
        pkg = _pkg("p1", created_by="u1", deadline=_outside_window())
        invs = [_inv("i1", pkg_id="p1", status="sent", company="A")]
        db = FakeDB(bid_packages=[pkg], bid_invitations=invs, users=[creator])
        mock = MagicMock(return_value={"id": "n"})

        result = _run(db, notification_creator=mock)

        assert result["packages_affected"] == 0
        mock.assert_not_called()
        assert invs[0]["status"] == "sent"
