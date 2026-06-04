"""Task 8.1.5 — read paths return proposed_start_date.

Drives the service helpers directly (fetch_submission_detail and
load_draft_response) — the route is just a thin wrapper around these and
testing them in isolation avoids the dual-call-shape ambiguity (.single()
vs .limit(1) on the same `bid_submissions` table) that bites the
op-aware mock when used through TestClient.

Pattern matches backend/tests/bid_submission_detail/conftest.py:
build_chain returns a chain where every method returns the same chain,
and .execute() returns a result with .data set to the row/list passed in.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from app.services.vendor_portal_service import (
    fetch_submission_detail,
    load_draft_response,
)

from .conftest import (
    PROPOSED_START_ISO,
    SUBMISSION_ID,
)


def _build_chain(data):
    chain = MagicMock()
    result = MagicMock()
    result.data = data
    for m in (
        "select", "insert", "update", "delete",
        "eq", "neq", "in_", "is_", "order", "limit",
        "single", "maybe_single",
    ):
        getattr(chain, m).return_value = chain
    chain.execute.return_value = result
    return chain


def _db_for_submission(sub_row: dict, line_items=None, attachments=None) -> MagicMock:
    db = MagicMock()
    line_items = line_items or []
    attachments = attachments or []

    def _table(name):
        if name == "bid_submissions":
            return _build_chain(sub_row)
        if name == "bid_line_items":
            return _build_chain(line_items)
        if name == "bid_attachments":
            return _build_chain(attachments)
        if name == "bid_template_items":
            return _build_chain([])
        return _build_chain([])

    db.table.side_effect = _table
    return db


def _sub_row(*, proposed=PROPOSED_START_ISO) -> dict:
    return {
        "id": str(SUBMISSION_ID),
        "status": "submitted",
        "is_draft": False,
        "total_amount": "50000.00",
        "vendor_notes": "Notes.",
        "submitted_at": "2026-06-04T00:00:00+00:00",
        "updated_at": "2026-06-04T00:00:00+00:00",
        "proposed_start_date": proposed,
    }


def test_fetch_submission_detail_returns_proposed_start_date():
    db = _db_for_submission(_sub_row())
    resp = fetch_submission_detail(db, str(SUBMISSION_ID))
    # The Pydantic SubmissionResponse must expose the field, and the SELECT
    # must include it — both wire up together.
    assert str(resp.proposed_start_date) == PROPOSED_START_ISO


def test_fetch_submission_detail_null_proposed_start_date():
    db = _db_for_submission(_sub_row(proposed=None))
    resp = fetch_submission_detail(db, str(SUBMISSION_ID))
    assert resp.proposed_start_date is None


def _draft_sub_row(*, proposed=PROPOSED_START_ISO) -> dict:
    return {
        "id": str(SUBMISSION_ID),
        "vendor_notes": "Draft.",
        "total_amount": "12345.00",
        "updated_at": "2026-06-04T00:00:00+00:00",
        "proposed_start_date": proposed,
        "bid_invitations": {
            "bid_packages": {"bid_template_id": str(uuid4())}
        },
    }


def test_load_draft_response_returns_proposed_start_date():
    db = _db_for_submission(_draft_sub_row())
    resp = load_draft_response(db, str(SUBMISSION_ID))
    assert str(resp.proposed_start_date) == PROPOSED_START_ISO


def test_load_draft_response_null_proposed_start_date():
    db = _db_for_submission(_draft_sub_row(proposed=None))
    resp = load_draft_response(db, str(SUBMISSION_ID))
    assert resp.proposed_start_date is None
