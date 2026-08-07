"""
record_response outcome mapping + PM notification fan-out (Phase 10.2).

The concurrency guarantees live in the fn_record_milestone_response RPC; here we
prove the service maps its outcomes and SQLSTATEs correctly and never surfaces a
raw 500 for the lost-race / stale cases. `first-response-wins` is simulated via
the two RPC signals a loser produces: the UNIQUE path (outcome
'already_answered') and the transition PT409 path.

The second half covers the PM fan-out: the service keys notifications on the
STATUS THE RPC RETURNS (never on the vendor's button), fires them only on the
winning transition, and treats every send as best-effort so a dead mail provider
can never fail a response the database has already committed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import milestone_response_service as svc
from app.services.milestone_response_service import record_response

from .conftest import make_api_error

ALERT_ID = uuid4()
CONTACT_ID = uuid4()
MILESTONE_ID = uuid4()
PM_ID = str(uuid4())
NOW_ISO = datetime.now(timezone.utc).isoformat()


@pytest.fixture(autouse=True)
def comms(monkeypatch):
    """Replace the three comms helpers with doubles.

    Mirrors the no-response job suite: patch the module-level names the service
    imported, so nothing renders a template or writes a notification row.
    """
    pm_email = AsyncMock(return_value=True)
    delayed = MagicMock(return_value={"id": "notif-delayed"})
    completed = MagicMock(return_value={"id": "notif-completed"})
    monkeypatch.setattr(svc, "send_milestone_pm_alert_email", pm_email)
    monkeypatch.setattr(svc, "notify_milestone_delayed", delayed)
    monkeypatch.setattr(svc, "notify_milestone_completed", completed)
    return {"email": pm_email, "delayed": delayed, "completed": completed}


def _db_with_milestone(make_db, *, created_by: str | None = PM_ID):
    """A FakeDB carrying the one milestone row the owner lookup reads."""
    row: dict = {"id": str(MILESTONE_ID), "name": "Rough Grading Complete"}
    if created_by is not None:
        row["created_by"] = created_by
    return make_db({"milestones": [row]})


def _rpc_row(outcome: str, value: str, status: str) -> list[dict]:
    return [
        {
            "outcome": outcome,
            "recorded_value": value,
            "recorded_at": NOW_ISO,
            "milestone_status": status,
        }
    ]


async def _call(db, value: str = "yes"):
    return await record_response(
        db,
        milestone_alert_id=ALERT_ID,
        value=value,
        vendor_contact_id=CONTACT_ID,
        milestone_id=MILESTONE_ID,
        email_service=object(),
    )


# ── Outcome / SQLSTATE mapping (unchanged behaviour) ────────────────────────


async def test_recorded_outcome(make_db):
    db = _db_with_milestone(make_db)
    db.rpc_result = _rpc_row("recorded", "yes", "in_progress")
    res = await _call(db)
    assert res.outcome == "recorded"
    assert res.recorded_value == "yes"
    assert res.milestone_status == "in_progress"

    # Identity + business-today were passed to the RPC (never from a body).
    name, params = db.rpc_calls[0]
    assert name == "fn_record_milestone_response"
    assert params["p_vendor_contact_id"] == str(CONTACT_ID)
    assert params["p_response_value"] == "yes"
    assert "p_today" in params


async def test_already_answered_outcome_not_an_error(make_db):
    """The concurrent loser (UNIQUE path) → 200 already_answered, never a 500."""
    db = _db_with_milestone(make_db)
    db.rpc_result = _rpc_row("already_answered", "no", "delayed")
    res = await _call(db)
    assert res.outcome == "already_answered"
    assert res.recorded_value == "no"


async def test_pt409_maps_to_410(make_db):
    """Stale cycle / illegal action / terminal milestone → 410 (no longer current)."""
    db = _db_with_milestone(make_db)
    db.rpc_error = make_api_error("PT409", "stale")
    with pytest.raises(HTTPException) as ei:
        await _call(db)
    assert ei.value.status_code == 410


async def test_pt404_maps_to_404(make_db):
    db = _db_with_milestone(make_db)
    db.rpc_error = make_api_error("PT404")
    with pytest.raises(HTTPException) as ei:
        await _call(db)
    assert ei.value.status_code == 404


async def test_pt422_maps_to_422(make_db):
    db = _db_with_milestone(make_db)
    db.rpc_error = make_api_error("PT422")
    with pytest.raises(HTTPException) as ei:
        await _call(db)
    assert ei.value.status_code == 422


async def test_unexpected_error_maps_to_502_not_500(make_db):
    db = _db_with_milestone(make_db)
    db.rpc_error = make_api_error("XX000", "boom")
    with pytest.raises(HTTPException) as ei:
        await _call(db)
    assert ei.value.status_code == 502


# ── PM notification fan-out ─────────────────────────────────────────────────


async def test_delayed_sends_pm_email_and_in_app(make_db, comms):
    """Vendor 'no' → delayed → BOTH channels, addressed to the milestone's PM."""
    db = _db_with_milestone(make_db)
    db.rpc_result = _rpc_row("recorded", "no", "delayed")

    res = await _call(db, value="no")
    assert res.milestone_status == "delayed"

    comms["email"].assert_awaited_once()
    kwargs = comms["email"].await_args.kwargs
    assert kwargs["alert_type"] == "delay"
    assert str(kwargs["recipient_user_id"]) == PM_ID
    assert str(kwargs["milestone_id"]) == str(MILESTONE_ID)

    comms["delayed"].assert_called_once()
    assert str(comms["delayed"].call_args.args[1]) == str(MILESTONE_ID)
    comms["completed"].assert_not_called()


async def test_completed_is_in_app_only_no_email(make_db, comms):
    """Vendor completion 'yes' → completed → in-app ONLY (locked comms tiering)."""
    db = _db_with_milestone(make_db)
    db.rpc_result = _rpc_row("recorded", "yes", "completed")

    await _call(db)

    comms["completed"].assert_called_once()
    assert str(comms["completed"].call_args.args[1]) == str(MILESTONE_ID)
    comms["email"].assert_not_awaited()
    comms["delayed"].assert_not_called()


async def test_in_progress_notifies_nobody(make_db, comms):
    """An affirmative start/progress answer is not news; it stays silent."""
    db = _db_with_milestone(make_db)
    db.rpc_result = _rpc_row("recorded", "yes", "in_progress")

    await _call(db)

    comms["email"].assert_not_awaited()
    comms["delayed"].assert_not_called()
    comms["completed"].assert_not_called()


async def test_lost_race_notifies_nobody(make_db, comms):
    """The loser of a double-click carries a real status but must send NOTHING.

    `already_answered` returns the milestone's current status (which may well be
    'delayed'), so keying on status alone would double-notify. The guard is the
    outcome, not the status.
    """
    db = _db_with_milestone(make_db)
    db.rpc_result = _rpc_row("already_answered", "no", "delayed")

    res = await _call(db, value="no")
    assert res.outcome == "already_answered"

    comms["email"].assert_not_awaited()
    comms["delayed"].assert_not_called()
    comms["completed"].assert_not_called()


async def test_email_failure_does_not_fail_the_response(make_db, comms):
    """A dead provider must not undo a response the DB already committed."""
    comms["email"].side_effect = RuntimeError("smtp down")
    db = _db_with_milestone(make_db)
    db.rpc_result = _rpc_row("recorded", "no", "delayed")

    res = await _call(db, value="no")

    assert res.outcome == "recorded"
    assert res.recorded_value == "no"
    assert res.milestone_status == "delayed"
    # The in-app channel is independent of the email one.
    comms["delayed"].assert_called_once()


async def test_in_app_failure_does_not_fail_the_response(make_db, comms):
    """Same isolation in the other direction: the email still went out."""
    comms["delayed"].side_effect = RuntimeError("notifications table down")
    db = _db_with_milestone(make_db)
    db.rpc_result = _rpc_row("recorded", "no", "delayed")

    res = await _call(db, value="no")

    assert res.outcome == "recorded"
    assert res.milestone_status == "delayed"
    comms["email"].assert_awaited_once()


async def test_completed_in_app_failure_does_not_fail_the_response(make_db, comms):
    comms["completed"].side_effect = RuntimeError("boom")
    db = _db_with_milestone(make_db)
    db.rpc_result = _rpc_row("recorded", "yes", "completed")

    res = await _call(db)

    assert res.outcome == "recorded"
    assert res.milestone_status == "completed"


async def test_unresolvable_owner_skips_email_without_crashing(make_db, comms):
    """No created_by → nobody to address the email to. Skip, don't raise."""
    db = _db_with_milestone(make_db, created_by=None)
    db.rpc_result = _rpc_row("recorded", "no", "delayed")

    res = await _call(db, value="no")

    assert res.outcome == "recorded"
    comms["email"].assert_not_awaited()
    # The in-app helper resolves the owner itself and no-ops the same way.
    comms["delayed"].assert_called_once()
