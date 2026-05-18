"""
Shared fixtures for per-vendor bid revision Step-3 tests
(finalize branch + revision prefill endpoint).

Vendor-portal endpoints authenticate via the vendor JWT
(`get_vendor_context`), so these tests override BOTH `get_supabase`
and `get_vendor_context`. The op-aware Supabase mock is the same shape
used by the Step-1/2 suites (keyed by table + op).
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
from app.services.email_service import get_email_service

# ── Deterministic IDs ──────────────────────────────────────────────────────

VENDOR_ID = uuid4()
VENDOR_CONTACT_ID = uuid4()
INVITATION_ID = uuid4()
BID_PACKAGE_ID = uuid4()
TASK_ID = uuid4()
SUBMISSION_ID = uuid4()
REVISION_REQUEST_ID = uuid4()
OTHER_SUBMISSION_ID = uuid4()
OTHER_VENDOR_ID = uuid4()


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


# ── Row builders ───────────────────────────────────────────────────────────


def owned_submission_row(**overrides) -> dict:
    """Flat bid_submissions row as returned to _fetch_owned_submission."""
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": str(SUBMISSION_ID),
        "bid_invitation_id": str(INVITATION_ID),
        "vendor_id": str(VENDOR_ID),
        "status": "draft",
        "is_draft": True,
        "total_amount": "50000.00",
        "vendor_notes": "Original notes.",
        "submitted_at": None,
        "updated_at": now,
    }
    row.update(overrides)
    return row


def committed_submission_row(**overrides) -> dict:
    row = owned_submission_row(
        status="submitted",
        is_draft=False,
        submitted_at=datetime.now(timezone.utc).isoformat(),
    )
    row.update(overrides)
    return row


def revision_request_row(**overrides) -> dict:
    row = {
        "id": str(REVISION_REQUEST_ID),
        "bid_invitation_id": str(INVITATION_ID),
        "original_submission_id": str(SUBMISSION_ID),
        "pm_note": "Please re-price line 3.",
        "revision_deadline": _future(),
        "status": "pending",
    }
    row.update(overrides)
    return row


def template_item_rows() -> list[dict]:
    return [
        {
            "id": str(uuid4()),
            "description": "Site prep",
            "item_type": "lump_sum",
            "unit_of_measure": None,
            "sort_order": 0,
        },
        {
            "id": str(uuid4()),
            "description": "Excavation",
            "item_type": "unit_price",
            "unit_of_measure": "CY",
            "sort_order": 1,
        },
    ]


def line_item_rows() -> list[dict]:
    return [
        {
            "description": "Site prep",
            "item_type": "lump_sum",
            "quantity": None,
            "unit_of_measure": None,
            "unit_price": None,
            "lump_sum_amount": "12500.00",
            "line_total": "12500.00",
            "sort_order": 0,
        },
        {
            "description": "Excavation",
            "item_type": "unit_price",
            "quantity": "300",
            "unit_of_measure": "CY",
            "unit_price": "100.00",
            "lump_sum_amount": None,
            "line_total": "30000.00",
            "sort_order": 1,
        },
    ]


# ── Op-aware Supabase mock ─────────────────────────────────────────────────


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


def vendor_ctx(*, revision: bool = False, vendor_id=None) -> VendorContext:
    return VendorContext(
        vendor_id=vendor_id or VENDOR_ID,
        vendor_contact_id=VENDOR_CONTACT_ID,
        bid_invitation_id=INVITATION_ID,
        bid_package_id=BID_PACKAGE_ID,
        task_id=TASK_ID,
        bid_revision_request_id=REVISION_REQUEST_ID if revision else None,
    )


@pytest.fixture()
def client_factory():
    """make(spec, *, ctx) → TestClient with db + vendor-ctx overrides."""

    def _make(spec: dict, *, ctx: VendorContext):
        app.dependency_overrides[get_supabase] = lambda: make_db(spec)
        app.dependency_overrides[get_vendor_context] = lambda: ctx
        app.dependency_overrides[get_email_service] = lambda: MagicMock()
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()
