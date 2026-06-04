"""Task 8.1.5 — bid-context's existing_draft.proposed_start_date round-trip.

This is the auto-save resume path: vendor saves a draft → closes the tab
→ reopens the magic link. The bid-context endpoint embeds
`existing_draft` via `_fetch_existing_draft`, which the SPA passes to
HYDRATE_FROM_DRAFT. If `proposed_start_date` is missing from this read,
the vendor sees an empty date field on resume even though the row has
the value persisted.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from app.services.vendor_portal_service import _fetch_existing_draft

from .conftest import PROPOSED_START_ISO


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


def _draft_db(*, proposed) -> MagicMock:
    """Mock returns one in-progress draft row with the given proposed date."""
    db = MagicMock()
    draft_row = {
        "id": str(uuid4()),
        "vendor_notes": "Mid-edit notes",
        "total_amount": "1000.00",
        "updated_at": "2026-06-04T00:00:00+00:00",
        "is_draft": True,
        "proposed_start_date": proposed,
    }

    def _table(name):
        if name == "bid_submissions":
            return _build_chain([draft_row])
        if name == "bid_line_items":
            return _build_chain([])
        if name == "bid_attachments":
            return _build_chain([])
        return _build_chain([])

    db.table.side_effect = _table
    return db


def test_existing_draft_returns_proposed_start_date_when_set():
    db = _draft_db(proposed=PROPOSED_START_ISO)
    draft = _fetch_existing_draft(db, uuid4(), template_items=[])
    assert draft is not None
    assert str(draft.proposed_start_date) == PROPOSED_START_ISO


def test_existing_draft_returns_null_when_field_is_null():
    db = _draft_db(proposed=None)
    draft = _fetch_existing_draft(db, uuid4(), template_items=[])
    assert draft is not None
    assert draft.proposed_start_date is None
