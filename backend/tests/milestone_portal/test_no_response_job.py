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

from app.jobs import milestone_no_response as job
from app.services.milestone_service import MilestoneError

# 2026-07-10 Fri (sent) → 2026-07-15 Wed (today) = 3 working days.
TODAY = date(2026, 7, 15)
SENT_FRI = "2026-07-10T12:00:00+00:00"
SENT_MON = "2026-07-13T12:00:00+00:00"  # Mon -> Wed = 2 working days (not due)


@pytest.fixture(autouse=True)
def _patch_clock_and_side_effects(monkeypatch):
    monkeypatch.setattr(job, "business_today", lambda: TODAY)
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
