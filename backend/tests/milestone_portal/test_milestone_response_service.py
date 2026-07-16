"""
record_response outcome mapping (Phase 10.2).

The concurrency guarantees live in the fn_record_milestone_response RPC; here we
prove the service maps its outcomes and SQLSTATEs correctly and never surfaces a
raw 500 for the lost-race / stale cases. `first-response-wins` is simulated via
the two RPC signals a loser produces: the UNIQUE path (outcome
'already_answered') and the transition PT409 path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.milestone_response_service import record_response

from .conftest import make_api_error

ALERT_ID = uuid4()
CONTACT_ID = uuid4()
NOW_ISO = datetime.now(timezone.utc).isoformat()


def _call(db):
    return record_response(
        db, milestone_alert_id=ALERT_ID, value="yes", vendor_contact_id=CONTACT_ID
    )


def test_recorded_outcome(make_db):
    db = make_db()
    db.rpc_result = [
        {
            "outcome": "recorded",
            "recorded_value": "yes",
            "recorded_at": NOW_ISO,
            "milestone_status": "in_progress",
        }
    ]
    res = _call(db)
    assert res.outcome == "recorded"
    assert res.recorded_value == "yes"
    assert res.milestone_status == "in_progress"

    # Identity + business-today were passed to the RPC (never from a body).
    name, params = db.rpc_calls[0]
    assert name == "fn_record_milestone_response"
    assert params["p_vendor_contact_id"] == str(CONTACT_ID)
    assert params["p_response_value"] == "yes"
    assert "p_today" in params


def test_already_answered_outcome_not_an_error(make_db):
    """The concurrent loser (UNIQUE path) → 200 already_answered, never a 500."""
    db = make_db()
    db.rpc_result = [
        {
            "outcome": "already_answered",
            "recorded_value": "no",
            "recorded_at": NOW_ISO,
            "milestone_status": "delayed",
        }
    ]
    res = _call(db)
    assert res.outcome == "already_answered"
    assert res.recorded_value == "no"


def test_pt409_maps_to_410(make_db):
    """Stale cycle / illegal action / terminal milestone → 410 (no longer current)."""
    db = make_db()
    db.rpc_error = make_api_error("PT409", "stale")
    with pytest.raises(HTTPException) as ei:
        _call(db)
    assert ei.value.status_code == 410


def test_pt404_maps_to_404(make_db):
    db = make_db()
    db.rpc_error = make_api_error("PT404")
    with pytest.raises(HTTPException) as ei:
        _call(db)
    assert ei.value.status_code == 404


def test_pt422_maps_to_422(make_db):
    db = make_db()
    db.rpc_error = make_api_error("PT422")
    with pytest.raises(HTTPException) as ei:
        _call(db)
    assert ei.value.status_code == 422


def test_unexpected_error_maps_to_502_not_500(make_db):
    db = make_db()
    db.rpc_error = make_api_error("XX000", "boom")
    with pytest.raises(HTTPException) as ei:
        _call(db)
    assert ei.value.status_code == 502
