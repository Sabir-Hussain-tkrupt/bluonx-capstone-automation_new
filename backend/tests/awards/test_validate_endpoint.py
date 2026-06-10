"""Preview endpoint tests — GET /api/v1/awards/validate/{bid_submission_id} (Task 9.1).

Read-only dry-run: structured result on 200, a blocking result still returns
200 (so the UI can render *why* it's blocked — the 422 hard-reject belongs to
award-create in 9.2/9.5), 404 on unknown submission, and no write ever occurs.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app

from .conftest import SUBMISSION_ID, VENDOR_ID

URL = f"/api/v1/awards/validate/{SUBMISSION_ID}"

# Clock-independent clean row: insurance far-future, valid through project end.
CLEAN_ROW = {
    "total_amount": "100000.00",
    "proposed_start_date": "2026-07-10",
    "vendor_id": str(VENDOR_ID),
    "is_draft": False,
    "is_superseded": False,
    "status": "submitted",
    "is_direct_assign": False,
    "vendors": {
        "insurance_expiration_date": "2099-01-01",
        "bonding_capacity": "200000.00",
        "max_active_jobs": 5,
        "current_active_jobs": 2,
        "onboarding_status": "complete",
    },
    "bid_invitations": {
        "bid_packages": {
            "desired_start_date": "2026-07-15",
            "deadline": "2026-06-01",
            "status": "open",
            "tasks": {
                "budget_estimate": "100000.00",
                "project_id": str(uuid4()),
                "projects": {"estimated_end_date": "2098-12-31"},
            },
        },
    },
}


def _row(**overrides) -> dict:
    return {**CLEAN_ROW, **overrides}


def test_clean_submission_returns_structured_result(client_factory):
    c = client_factory({"bid_submissions": {"select": _row()}})
    r = c.get(URL)
    assert r.status_code == 200
    body = r.json()
    assert body["rubric_version"] == "preaward-v1"
    assert body["can_award"] is True
    assert body["requires_override"] is False
    assert len(body["checks"]) == 6


def test_superseded_returns_200_with_block_detail(client_factory):
    c = client_factory({"bid_submissions": {"select": _row(is_superseded=True)}})
    r = c.get(URL)
    # Blocking is a 200 here, NOT a 422 — the preview explains the block.
    assert r.status_code == 200
    body = r.json()
    assert body["can_award"] is False
    assert body["has_blocking"] is True
    elig = next(c for c in body["checks"] if c["check"] == "submission_eligibility")
    assert elig["severity"] == "block"


def test_unknown_submission_returns_404(client_factory):
    c = client_factory({"bid_submissions": {"select": []}})
    r = c.get(URL)
    assert r.status_code == 404


def _no_write_db(row: dict) -> MagicMock:
    """A db whose write verbs raise — proves the endpoint never writes."""
    client = MagicMock()

    def _table(_name: str):
        chain = MagicMock()
        for m in ("select", "eq", "neq", "in_", "is_", "order", "limit",
                  "single", "maybe_single"):
            getattr(chain, m).return_value = chain

        def _fail(*_a, **_k):
            raise AssertionError("write attempted on a read-only endpoint")

        chain.insert.side_effect = _fail
        chain.update.side_effect = _fail
        chain.delete.side_effect = _fail
        res = MagicMock()
        res.data = row
        chain.execute.return_value = res
        return chain

    client.table.side_effect = _table
    return client


def test_no_write_occurs(authed_user):
    db = _no_write_db(_row())
    app.dependency_overrides[get_current_active_user] = lambda: authed_user
    app.dependency_overrides[get_supabase] = lambda: db
    try:
        r = TestClient(app).get(URL)
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()
