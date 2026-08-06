"""
Milestone no-response escalation job (Phase 10.2).

Driven by FakeDB with the transition + email + notify collaborators patched, so
we assert the job's DECISIONS: escalate only after 3 working days, once per
check, never on a bounced email, never on a paused/terminal or stale-cycle
milestone.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.jobs import milestone_daily_checkin as checkin_job
from app.jobs import milestone_no_response as job
from app.services.email_service import EmailService, MockEmailProvider
from app.services.milestone_service import MilestoneError

from .conftest import FakeDB

# 2026-07-10 Fri (sent) → 2026-07-15 Wed (today) = 3 working days.
TODAY = date(2026, 7, 15)
SENT_FRI = "2026-07-10T12:00:00+00:00"
SENT_MON = "2026-07-13T12:00:00+00:00"  # Mon -> Wed = 2 working days (not due)


class FakeCalendar:
    """Stand-in for BusinessCalendar with a configurable holiday list.

    The real class talks to the database. This suite's FakeDB has a single
    rpc_result and cannot dispatch by function name, so a live BusinessCalendar
    would collide with the transition_milestone stubbing. The arithmetic itself
    is covered against the real database in tests/holidays/.
    """

    holidays: list = []

    def __init__(self, db=None):
        self.db = db

    def prime_holidays(self, start, end):
        self.primed = (start, end)

    def holidays_in(self, start, end):
        return [h for h in self.holidays if start < h.date <= end]

    def business_days_since(self, sent, today):
        if today <= sent:
            return 0
        from datetime import timedelta

        holiday_dates = {h.date for h in self.holidays}
        count = 0
        cursor = sent + timedelta(days=1)
        while cursor <= today:
            if cursor.weekday() < 5 and cursor not in holiday_dates:
                count += 1
            cursor += timedelta(days=1)
        return count

    def add_business_days(self, start, days):
        from datetime import timedelta

        holiday_dates = {h.date for h in self.holidays}
        cursor, remaining = start, days
        while remaining > 0:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5 and cursor not in holiday_dates:
                remaining -= 1
        return cursor


@pytest.fixture(autouse=True)
def _patch_clock_and_side_effects(monkeypatch):
    monkeypatch.setattr(job, "business_today", lambda: TODAY)
    FakeCalendar.holidays = []
    monkeypatch.setattr(job, "BusinessCalendar", FakeCalendar)
    esc = MagicMock(return_value={"id": "ms"})
    pm_email = AsyncMock(return_value=True)
    notify = MagicMock(return_value={"id": "notif"})
    monkeypatch.setattr(job, "escalate_no_response", esc)
    monkeypatch.setattr(job, "send_milestone_pm_alert_email", pm_email)
    monkeypatch.setattr(job, "notify_milestone_unresponsive", notify)
    return {"escalate": esc, "pm_email": pm_email, "notify": notify}


def _alert(
    *,
    alert_id=None,
    milestone_id=None,
    cycle_alert=1,
    cycle_ms=1,
    status="in_progress",
    created_at=SENT_FRI,
    email_status=None,
    created_by="pm-1",
    alert_type="progress_check",
):
    alert_id = alert_id or str(uuid4())
    milestone_id = milestone_id or str(uuid4())
    return {
        "id": alert_id,
        "milestone_id": milestone_id,
        "alert_type": alert_type,
        "recipient_type": "vendor",
        "cycle_number": cycle_alert,
        "created_at": created_at,
        "milestones": {
            "id": milestone_id,
            "status": status,
            "cycle_number": cycle_ms,
            "created_by": created_by,
        },
        "email_log": {"status": email_status} if email_status else None,
    }


def _db(make_db, alerts, *, responses=None, markers=None):
    tables = {
        "milestone_alerts": list(alerts) + list(markers or []),
        "milestone_responses": responses or [],
    }
    return make_db(tables)


async def _run(db):
    return await job.run_milestone_no_response_escalation(
        db, email_service=AsyncMock(), notification_creator=MagicMock()
    )


async def test_escalates_after_three_working_days(make_db, _patch_clock_and_side_effects):
    a = _alert()
    db = _db(make_db, [a])
    counts = await _run(db)

    assert counts["escalated"] == 1
    _patch_clock_and_side_effects["escalate"].assert_called_once()
    _patch_clock_and_side_effects["pm_email"].assert_awaited_once()
    _patch_clock_and_side_effects["notify"].assert_called_once()
    # Dedup marker written for this milestone + cycle.
    markers = [
        rows
        for t, rows in db.inserts
        if t == "milestone_alerts" and rows[0]["alert_type"] == "no_response_alert"
    ]
    assert len(markers) == 1


async def test_not_due_before_three_working_days(make_db, _patch_clock_and_side_effects):
    db = _db(make_db, [_alert(created_at=SENT_MON)])
    counts = await _run(db)
    assert counts["escalated"] == 0
    assert counts["skipped_not_due"] == 1
    _patch_clock_and_side_effects["escalate"].assert_not_called()


async def test_answered_is_not_silence(make_db, _patch_clock_and_side_effects):
    a = _alert()
    db = _db(make_db, [a], responses=[{"milestone_alert_id": a["id"]}])
    counts = await _run(db)
    assert counts["skipped_answered"] == 1
    _patch_clock_and_side_effects["escalate"].assert_not_called()


async def test_once_per_check_dedup(make_db, _patch_clock_and_side_effects):
    a = _alert()
    marker = {
        "id": str(uuid4()),
        "milestone_id": a["milestone_id"],
        "alert_type": "no_response_alert",
        "recipient_type": "pm",
        "cycle_number": 1,
    }
    db = _db(make_db, [a], markers=[marker])
    counts = await _run(db)
    assert counts["skipped_already_escalated"] == 1
    _patch_clock_and_side_effects["escalate"].assert_not_called()


@pytest.mark.parametrize("status", ["delayed", "unresponsive", "completed", "cancelled"])
async def test_paused_or_terminal_skipped(make_db, _patch_clock_and_side_effects, status):
    db = _db(make_db, [_alert(status=status)])
    counts = await _run(db)
    assert counts["skipped_not_escalatable"] == 1
    _patch_clock_and_side_effects["escalate"].assert_not_called()


async def test_stale_cycle_skipped(make_db, _patch_clock_and_side_effects):
    db = _db(make_db, [_alert(cycle_alert=1, cycle_ms=2)])
    counts = await _run(db)
    assert counts["skipped_stale_cycle"] == 1
    _patch_clock_and_side_effects["escalate"].assert_not_called()


async def test_bounced_email_is_not_silence(make_db, _patch_clock_and_side_effects):
    a = _alert(email_status="bounced")
    notifier = MagicMock()
    db = _db(make_db, [a])
    counts = await job.run_milestone_no_response_escalation(
        db, email_service=AsyncMock(), notification_creator=notifier
    )
    assert counts["bounce_notified"] == 1
    assert counts["escalated"] == 0
    _patch_clock_and_side_effects["escalate"].assert_not_called()
    # PM told about the delivery failure, not the (non-)silence.
    notifier.assert_called_once()
    assert notifier.call_args.kwargs["notification_type"] == "milestone_delivery_failed"


async def test_transition_conflict_is_swallowed(make_db, _patch_clock_and_side_effects):
    """If the milestone moved between query and transition, PT409 → skip, not crash."""
    _patch_clock_and_side_effects["escalate"].side_effect = MilestoneError(409, "moved")
    db = _db(make_db, [_alert()])
    counts = await _run(db)
    assert counts["escalated"] == 0
    assert counts["skipped_already_escalated"] == 1


# ── Bounce rule, end to end with the check-in job (Phase 10.3) ─────────────
#
# The tests above hand-build the email_log embed, so they pass even when nothing
# populates milestone_alerts.email_log_id, which was exactly the live defect: the
# bounce rule was written, tested, and inert. This test earns the rule instead. It
# runs the real EmailService and the real send helper so the log id genuinely flows
# provider → email_log → EmailSendResult.log_id → milestone_alerts.email_log_id, and
# resolves the embed off that FK the way PostgREST does. Break the linkage anywhere
# and the embed goes empty, the bounce reads as silence, and this test fails.

SENT_DAY = date(2026, 7, 10)  # the Friday the check-in went out (3 working days back)


class _EmbedDB(FakeDB):
    """FakeDB that resolves the two embeds the no-response job's query reads.

    email_log resolves ONLY via milestone_alerts.email_log_id, exactly as the real
    FK embed does: an unstamped alert yields no delivery status.
    """

    def _resolve(self, table, op, filters, payload, single, limit):
        result = super()._resolve(table, op, filters, payload, single, limit)
        if table != "milestone_alerts" or op != "select":
            return result
        if not isinstance(result.data, list):
            return result

        embedded = []
        for row in result.data:
            row = dict(row)
            row["milestones"] = next(
                (
                    m
                    for m in self.tables.get("milestones", [])
                    if m["id"] == row.get("milestone_id")
                ),
                {},
            )
            log = next(
                (
                    e
                    for e in self.tables.get("email_log", [])
                    if e["id"] == row.get("email_log_id")
                ),
                None,
            )
            row["email_log"] = {"status": log["status"]} if log else None
            embedded.append(row)
        return type(result)(embedded)


def _e2e_db() -> _EmbedDB:
    """One milestone with everything the check-in send path reads."""
    return _EmbedDB(
        {
            "v_milestone_overview": [
                {
                    "milestone_id": "m1",
                    "status": "in_progress",
                    "cycle_number": 1,
                    "start_date": SENT_DAY.isoformat(),
                    "end_date": "2026-08-30",
                }
            ],
            "milestones": [
                {
                    "id": "m1",
                    "status": "in_progress",
                    "cycle_number": 1,
                    "created_by": "pm-1",
                    "name": "Rough Grading Complete",
                    "start_date": SENT_DAY.isoformat(),
                    "end_date": "2026-08-30",
                    "task_id": "t1",
                    "tasks": {
                        "id": "t1",
                        "name": "Rough Grading",
                        "project_id": "p1",
                        "projects": {"name": "North Yard"},
                    },
                    "contracts": {
                        "vendor_id": "v1",
                        "vendors": {"company_name": "Summit Earthworks LLC"},
                    },
                }
            ],
            "vendor_contacts": [
                {
                    "id": "vc1",
                    "vendor_id": "v1",
                    "is_primary": True,
                    "full_name": "Marcus Delgado",
                    "email": "marcus@summit.example",
                }
            ],
            "milestone_alerts": [],
            "email_log": [],
        }
    )


async def test_bounced_checkin_is_not_escalated_end_to_end(
    monkeypatch, _patch_clock_and_side_effects
):
    db = _e2e_db()

    # ── 1. The check-in job sends today's start check, for real. ──────────
    monkeypatch.setattr(checkin_job, "business_today", lambda: SENT_DAY)

    def _mint(fake_db, *, milestone_id, alert_type, cycle_number):
        fake_db.table("milestone_alerts").insert(
            {
                "milestone_id": milestone_id,
                "alert_type": alert_type,
                "recipient_type": "vendor",
                "cycle_number": cycle_number,
                "created_at": f"{SENT_DAY.isoformat()}T12:00:00+00:00",
            }
        ).execute()
        return ("raw-token", "https://portal.test/milestone/raw-token")

    monkeypatch.setattr(checkin_job, "mint_checkin_token", _mint)

    email_service = EmailService(provider=MockEmailProvider(), db_client=db)
    sent = await checkin_job.run_milestone_daily_checkin(db, email_service)
    assert sent["start_sent"] == 1

    # The linkage Part A exists for: a real email_log row, stamped on the alert.
    alert = db.tables["milestone_alerts"][0]
    log_row = db.tables["email_log"][0]
    assert alert["email_log_id"] == log_row["id"]

    # ── 2. SES reports a bounce (as the SNS webhook would). ───────────────
    log_row["status"] = "bounced"

    # ── 3. Three working days later, the vendor has "not answered". ───────
    counts = await job.run_milestone_no_response_escalation(
        db, email_service=AsyncMock(), notification_creator=MagicMock()
    )

    # The vendor never got the email, so this is a delivery problem, not silence.
    assert counts["escalated"] == 0
    assert counts["bounce_notified"] == 1
    _patch_clock_and_side_effects["escalate"].assert_not_called()


# ── The reason string ───────────────────────────────────────────────────────
#
# milestone_events.note is the ONLY place the working-day rule is ever visible
# to a PM: the check-in email carries no reply-by date, and the milestone date
# picker gives no holiday warning. So the note has to explain the timing, not
# just assert a number.


async def test_note_explains_the_timing_with_no_holidays(
    make_db, _patch_clock_and_side_effects
):
    db = _db(make_db, [_alert()])
    await _run(db)

    note = _patch_clock_and_side_effects["escalate"].call_args.kwargs["note"]

    # The pre-holiday sentence is preserved verbatim, so old log greps still hit.
    assert note.startswith("No vendor response to progress check after 3 working days.")
    assert "Check-in sent Jul 10, 2026" in note
    assert "a reply was due by end of Jul 15, 2026" in note
    assert "No holidays fell in this window." in note


async def test_note_names_the_holiday_that_moved_the_deadline(
    make_db, _patch_clock_and_side_effects
):
    """Sent Fri Jul 10 with Mon Jul 13 a holiday: only Tue and Wed count, so the
    milestone is not yet due and the deadline has moved to Thursday."""
    from app.core.time import Holiday

    FakeCalendar.holidays = [Holiday(date(2026, 7, 13), "Planted Holiday")]

    db = _db(make_db, [_alert()])
    counts = await _run(db)

    # 2 working days, not 3 — the holiday bought the vendor another day.
    assert counts["escalated"] == 0
    assert counts["skipped_not_due"] == 1


async def test_note_lists_holidays_when_the_window_is_long_enough(
    make_db, _patch_clock_and_side_effects
):
    """Sent Wed Jul 8 with Fri Jul 10 a holiday: Thu + Mon + Tue = 3 working
    days by Wed Jul 15, so it escalates and the note has to say why it took
    five calendar days."""
    from app.core.time import Holiday

    FakeCalendar.holidays = [Holiday(date(2026, 7, 10), "Planted Holiday")]

    db = _db(make_db, [_alert(created_at="2026-07-08T12:00:00+00:00")])
    counts = await _run(db)

    assert counts["escalated"] == 1
    note = _patch_clock_and_side_effects["escalate"].call_args.kwargs["note"]
    assert "1 holiday excluded from the count: Planted Holiday on Jul 10, 2026." in note
    assert "No holidays fell in this window." not in note
