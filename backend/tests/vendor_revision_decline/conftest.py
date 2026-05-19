"""
Fixtures for the SPA-mediated vendor revision-decline endpoint (B.5).

POST /api/v1/vendor-portal/revision-requests/{id}/decline authenticates via
the vendor JWT (`get_vendor_context`), so these tests override BOTH
`get_supabase` and `get_vendor_context` — same convention as the
vendor_revision_finalize suite. The 401 path deliberately does NOT override
`get_vendor_context` so the real bearer dependency runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.supabase_client import get_supabase
from app.core.vendor_auth import VendorContext, get_vendor_context
from app.main import app

# ── Deterministic IDs ──────────────────────────────────────────────────────

VENDOR_ID = uuid4()
VENDOR_CONTACT_ID = uuid4()
INVITATION_ID = uuid4()
BID_PACKAGE_ID = uuid4()
TASK_ID = uuid4()
SUBMISSION_ID = uuid4()
REVISION_REQUEST_ID = uuid4()
OTHER_REVISION_REQUEST_ID = uuid4()

BASE = f"/api/v1/vendor-portal/revision-requests/{REVISION_REQUEST_ID}/decline"


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


def revision_request_row(**overrides) -> dict:
    """Full bid_revision_requests row in the BidRevisionRequestResponse shape."""
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": str(REVISION_REQUEST_ID),
        "bid_invitation_id": str(INVITATION_ID),
        "original_submission_id": str(SUBMISSION_ID),
        "pm_note": "Please re-price line 3.",
        "revision_deadline": _future(),
        "status": "declined",
        "decline_reason": None,
        "requested_by": str(uuid4()),
        "requested_at": now,
        "responded_at": now,
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return row


# ── Op-aware Supabase mock (same shape as the sibling suites) ───────────────


def make_db(spec: dict) -> MagicMock:
    """spec = {table: {"select": data|Exc, "update": ..., "default": ...}}."""
    client = MagicMock()

    def _table(name: str):
        tspec = spec.get(name, {})
        chain = MagicMock()
        state = {"op": "select"}

        def _setop(op):
            def _f(*_a, **_k):
                state["op"] = op
                return chain

            return _f

        chain.select.side_effect = _setop("select")
        chain.insert.side_effect = _setop("insert")
        chain.update.side_effect = _setop("update")
        chain.delete.side_effect = _setop("delete")
        for m in (
            "eq", "neq", "in_", "is_", "order", "limit",
            "single", "maybe_single", "gt", "lt", "gte", "lte",
        ):
            getattr(chain, m).return_value = chain

        def _execute(*_a, **_k):
            data = tspec.get(state["op"], tspec.get("default", []))
            if isinstance(data, Exception):
                raise data
            res = MagicMock()
            res.data = data
            return res

        chain.execute.side_effect = _execute
        return chain

    client.table.side_effect = _table
    return client


def vendor_ctx(
    *, revision_request_id=REVISION_REQUEST_ID, with_revision: bool = True
) -> VendorContext:
    """A vendor context. with_revision=False ⇒ an initial-bid JWT (no claim)."""
    return VendorContext(
        vendor_id=VENDOR_ID,
        vendor_contact_id=VENDOR_CONTACT_ID,
        bid_invitation_id=INVITATION_ID,
        bid_package_id=BID_PACKAGE_ID,
        task_id=TASK_ID,
        bid_revision_request_id=revision_request_id if with_revision else None,
    )


@pytest.fixture()
def client_factory():
    """make(spec, *, ctx) → TestClient with db + vendor-ctx overrides.

    Pass ctx=None to exercise the real bearer dependency (401 path).
    """

    def _make(spec: dict, *, ctx: VendorContext | None):
        app.dependency_overrides[get_supabase] = lambda: make_db(spec)
        if ctx is not None:
            app.dependency_overrides[get_vendor_context] = lambda: ctx
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()
