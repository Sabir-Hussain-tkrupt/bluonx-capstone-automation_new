"""
Step 3 read-path audit (service-level).

_fetch_submitted_bids must exclude superseded submissions from the
package comparison/chart data source. _transform_invitation must
deep-link the current (non-superseded) submission, with a safe
fallback for pre-revision / single / direct-assign rows.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from app.services.invitation_tracking_service import (
    _fetch_submitted_bids,
    _transform_invitation,
)


def _recording_db(rows):
    """Chain mock that records every .eq(col, val) pair."""
    calls: list[tuple] = []
    chain = MagicMock()
    chain.select.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain

    def _eq(col, val):
        calls.append((col, val))
        return chain

    chain.eq.side_effect = _eq
    result = MagicMock()
    result.data = rows
    chain.execute.return_value = result

    db = MagicMock()
    db.table.return_value = chain
    return db, calls


def test_fetch_submitted_bids_excludes_superseded():
    db, calls = _recording_db([])
    _fetch_submitted_bids(db, uuid4())
    assert ("is_superseded", False) in calls


def test_transform_invitation_picks_non_superseded():
    a, b = str(uuid4()), str(uuid4())
    row = {
        "id": str(uuid4()),
        "vendor_id": str(uuid4()),
        "bid_submissions": [
            {"id": a, "is_superseded": True},
            {"id": b, "is_superseded": False},
        ],
    }
    assert _transform_invitation(row)["bid_submission_id"] == b


def test_transform_invitation_single_submission_unaffected():
    sid = str(uuid4())
    row = {
        "id": str(uuid4()),
        "vendor_id": str(uuid4()),
        "bid_submissions": [{"id": sid}],  # no is_superseded key (pre-revision)
    }
    assert _transform_invitation(row)["bid_submission_id"] == sid


def test_transform_invitation_no_submissions():
    row = {"id": str(uuid4()), "vendor_id": str(uuid4()), "bid_submissions": None}
    assert _transform_invitation(row)["bid_submission_id"] is None


# ── Draft leakage regression (Phase D+E QA) ───────────────────────────────


def test_fetch_submitted_bids_excludes_drafts():
    """Drafts (is_draft=TRUE) must not contribute to the chart, even when
    is_superseded is FALSE."""
    db, calls = _recording_db([])
    _fetch_submitted_bids(db, uuid4())
    assert ("is_draft", False) in calls


def test_transform_invitation_only_draft_returns_none():
    """An invitation whose only submission is a draft has no current bid
    for display — bid_submission_id is None (NOT the draft's id)."""
    draft = str(uuid4())
    row = {
        "id": str(uuid4()),
        "vendor_id": str(uuid4()),
        "bid_submissions": [
            {"id": draft, "is_superseded": False, "is_draft": True},
        ],
    }
    assert _transform_invitation(row)["bid_submission_id"] is None


def test_transform_invitation_prefers_finalized_over_draft():
    """A draft revision in progress alongside a finalized original: the
    finalized original's id is current, never the draft's (filter, not
    array order)."""
    original, draft = str(uuid4()), str(uuid4())
    row = {
        "id": str(uuid4()),
        "vendor_id": str(uuid4()),
        "bid_submissions": [
            {"id": draft, "is_superseded": False, "is_draft": True},
            {"id": original, "is_superseded": False, "is_draft": False},
        ],
    }
    assert _transform_invitation(row)["bid_submission_id"] == original
