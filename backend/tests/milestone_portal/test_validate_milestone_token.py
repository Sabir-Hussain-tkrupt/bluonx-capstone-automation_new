"""
Gate ordering + scanner-safety for validate_milestone_token (Phase 10.2).

Driven by the in-memory FakeDB so we exercise the branch logic without a DB.
The load-bearing guarantees:
  - a GET/validate NEVER records a response (scanner pre-fetch safety);
  - a cycle-superseded (rescheduled) token is stale;
  - an already-answered check returns the recorded answer, not an error.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.milestone_portal_service import validate_milestone_token

RAW = "raw-token-abc"
HASH = hashlib.sha256(RAW.encode()).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _future() -> str:
    return _iso(datetime.now(timezone.utc) + timedelta(days=3))


def _past() -> str:
    return _iso(datetime.now(timezone.utc) - timedelta(hours=1))


def _tables(
    *,
    cycle_token=1,
    cycle_ms=1,
    status="in_progress",
    revoked=None,
    expires=None,
    is_used=False,
    alert_type="progress_check",
    responses=None,
):
    alert_id = str(uuid4())
    ms_id = str(uuid4())
    contact_id = str(uuid4())
    vendor_id = str(uuid4())
    return {
        "milestone_checkin_tokens": [
            {
                "id": str(uuid4()),
                "milestone_alert_id": alert_id,
                "milestone_id": ms_id,
                "vendor_contact_id": contact_id,
                "cycle_number": cycle_token,
                "token_hash": HASH,
                "expires_at": expires or _future(),
                "is_used": is_used,
                "revoked_at": revoked,
            }
        ],
        "milestones": [
            {
                "id": ms_id,
                "name": "Rough Grading",
                "end_date": "2026-08-01",
                "status": status,
                "cycle_number": cycle_ms,
                "tasks": {"name": "Grading", "project_id": "p1", "projects": {"name": "Proj"}},
                "contracts": {"vendor_id": vendor_id, "vendors": {"company_name": "Apex"}},
            }
        ],
        "milestone_alerts": [{"id": alert_id, "alert_type": alert_type}],
        "milestone_responses": [
            {**r, "milestone_alert_id": alert_id} for r in (responses or [])
        ],
    }, alert_id


def test_actionable_returns_jwt_and_context_and_no_response_write(make_db):
    tables, alert_id = _tables(alert_type="start_check")
    db = make_db(tables)

    res = validate_milestone_token(db, raw_token=RAW, client_ip="203.0.113.7")

    assert res.outcome == "actionable"
    assert res.jwt
    assert res.milestone_context is not None
    assert res.milestone_context.check_type == "start"
    assert str(res.milestone_context.milestone_alert_id) == alert_id
    # First-view audit write flipped is_used…
    assert any(t == "milestone_checkin_tokens" for t, _, _ in db.updates)
    # …but NO response was recorded (scanner pre-fetch safety).
    assert not any(t == "milestone_responses" for t, _ in db.inserts)


def test_unknown_token_404(make_db):
    db = make_db({"milestone_checkin_tokens": []})
    with pytest.raises(HTTPException) as ei:
        validate_milestone_token(db, raw_token=RAW, client_ip="ip")
    assert ei.value.status_code == 404


def test_revoked_token_410(make_db):
    tables, _ = _tables(revoked=_past())
    with pytest.raises(HTTPException) as ei:
        validate_milestone_token(make_db(tables), raw_token=RAW, client_ip="ip")
    assert ei.value.status_code == 410


def test_expired_token_410(make_db):
    tables, _ = _tables(expires=_past())
    with pytest.raises(HTTPException) as ei:
        validate_milestone_token(make_db(tables), raw_token=RAW, client_ip="ip")
    assert ei.value.status_code == 410


def test_cycle_mismatch_is_stale_410(make_db):
    tables, _ = _tables(cycle_token=1, cycle_ms=2)
    db = make_db(tables)
    with pytest.raises(HTTPException) as ei:
        validate_milestone_token(db, raw_token=RAW, client_ip="ip")
    assert ei.value.status_code == 410
    assert not any(t == "milestone_responses" for t, _ in db.inserts)


def test_already_answered_returns_recorded_no_jwt(make_db):
    answered_at = _iso(datetime.now(timezone.utc) - timedelta(hours=2))
    tables, _ = _tables(
        responses=[{"response_value": "yes", "responded_at": answered_at}]
    )
    db = make_db(tables)

    res = validate_milestone_token(db, raw_token=RAW, client_ip="ip")

    assert res.outcome == "already_answered"
    assert res.recorded_value == "yes"
    assert res.jwt is None
    assert not any(t == "milestone_responses" for t, _ in db.inserts)


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_terminal_milestone_410(make_db, status):
    tables, _ = _tables(status=status)
    with pytest.raises(HTTPException) as ei:
        validate_milestone_token(make_db(tables), raw_token=RAW, client_ip="ip")
    assert ei.value.status_code == 410


@pytest.mark.parametrize("status", ["delayed", "unresponsive"])
def test_paused_milestone_is_still_answerable(make_db, status):
    """A late reply resolves silence — delayed/unresponsive stay actionable."""
    tables, _ = _tables(status=status)
    res = validate_milestone_token(make_db(tables), raw_token=RAW, client_ip="ip")
    assert res.outcome == "actionable"
