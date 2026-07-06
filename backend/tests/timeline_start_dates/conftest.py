"""
Shared fixtures for Task 8.1.5 — timeline start dates.

Mirrors the op-aware Supabase mock pattern from
backend/tests/vendor_revision_finalize/conftest.py so the per-table dispatch
matches the rest of the vendor-portal suite. Bid-package-creation tests
reuse the same MagicMock chain pattern as backend/tests/bid_package_creation/.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.supabase_client import get_supabase
from app.core.vendor_auth import VendorContext, get_vendor_context
from app.main import app
from app.services.email_service import EmailSendResult, get_email_service


# ── Deterministic IDs ──────────────────────────────────────────────────────

VENDOR_ID = uuid4()
VENDOR_CONTACT_ID = uuid4()
INVITATION_ID = uuid4()
BID_PACKAGE_ID = uuid4()
TASK_ID = uuid4()
SUBMISSION_ID = uuid4()
REVISION_REQUEST_ID = uuid4()
PROJECT_ID = uuid4()
BID_TEMPLATE_ID = uuid4()
PM_USER_ID = uuid4()


# ── Date helpers ───────────────────────────────────────────────────────────

DESIRED_START_ISO = "2026-09-15"
PROPOSED_START_ISO = "2026-09-20"


def _future_dt() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()


# ── Row builders ───────────────────────────────────────────────────────────


def owned_submission_row(**overrides) -> dict:
    """Flat bid_submissions row as returned to _fetch_owned_submission.

    Includes proposed_start_date — implementation must SELECT it.
    """
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": str(SUBMISSION_ID),
        "bid_invitation_id": str(INVITATION_ID),
        "vendor_id": str(VENDOR_ID),
        "status": "draft",
        "is_draft": True,
        "total_amount": "50000.00",
        "vendor_notes": "Original notes.",
        "proposed_start_date": PROPOSED_START_ISO,
        # SoW attestation is unconditionally required at submit; a valid
        # all-CAPS value keeps these timeline tests focused on the date rule.
        "sow_attested_name": "APEX",
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
        "revision_deadline": _future_dt(),
        "status": "pending",
    }
    row.update(overrides)
    return row


def package_row(*, desired_start_date: str | None = DESIRED_START_ISO,
                status: str = "open", **overrides) -> dict:
    row = {
        "id": str(BID_PACKAGE_ID),
        "status": status,
        "deadline": _future_dt(),
        "desired_start_date": desired_start_date,
    }
    row.update(overrides)
    return row


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


# ── Bid-package creation fixtures (admin path) ─────────────────────────────


@pytest.fixture()
def mock_email_service() -> AsyncMock:
    svc = AsyncMock()
    svc.send_email.return_value = EmailSendResult(
        message_id=f"mock-{uuid4()}",
        status="sent",
        error=None,
    )
    return svc


@pytest.fixture()
def mock_template_renderer() -> MagicMock:
    renderer = MagicMock()
    renderer.render.side_effect = lambda *_a, **_k: "<html></html>"
    renderer.render_text.side_effect = lambda *_a, **_k: "plain"
    return renderer


@pytest.fixture()
def mock_supabase_admin() -> MagicMock:
    """Mock Supabase client for the admin bid-package service.

    SELECT-chains return empty (so the service skips its task / vendor /
    template validation block and proceeds straight to inserts), while
    INSERT-chains return a freshly created bid_packages row.

    This isolates the test from the bid_package_service's defensive
    validation logic — the contract under test is "what gets persisted",
    not "what gets validated".
    """
    client = MagicMock()
    bp_row = {
        "id": str(BID_PACKAGE_ID),
        "task_id": str(TASK_ID),
        "round_number": 1,
        "deadline": _future_dt(),
        "status": "open",
        "bid_template_id": str(BID_TEMPLATE_ID),
        "created_by": str(PM_USER_ID),
        "desired_start_date": DESIRED_START_ISO,
    }

    def _make_chain():
        chain = MagicMock()

        # SELECT path: any .select(...).eq(...).single().execute() yields
        # empty data → _query_one returns None → validation block skipped.
        select_exec = MagicMock()
        select_exec.execute.return_value = MagicMock(data=[])
        select_exec.eq.return_value = select_exec
        select_exec.is_.return_value = select_exec
        select_exec.single.return_value = select_exec
        select_exec.in_.return_value = select_exec
        select_exec.order.return_value = select_exec
        chain.select.return_value = select_exec

        # INSERT path: returns the bid_packages row (good for the first
        # insert; subsequent inserts just need a truthy data list).
        insert_exec = MagicMock()
        insert_exec.execute.return_value = MagicMock(data=[bp_row])
        insert_exec.eq.return_value = insert_exec
        chain.insert.return_value = insert_exec

        # UPDATE / DELETE chains — no-op data.
        upd_exec = MagicMock()
        upd_exec.execute.return_value = MagicMock(data=[])
        upd_exec.eq.return_value = upd_exec
        chain.update.return_value = upd_exec
        chain.delete.return_value = upd_exec

        return chain

    client.table.return_value = _make_chain()

    # Creation now happens via the atomic RPC; mirror the real return shape
    # (one invitation per vendor) and echo the desired_start_date back through
    # the package row so the response-shape tests pass.
    def _rpc(fn_name, params=None):
        result = MagicMock()
        if fn_name == "fn_create_bid_package_with_invitations":
            vendors = (params or {}).get("p_vendors", [])
            result.execute.return_value = MagicMock(data={
                "bid_package_id": str(BID_PACKAGE_ID),
                "round_number": 1,
                "invitations": [
                    {"vendor_id": v["vendor_id"], "invitation_id": str(uuid4())}
                    for v in vendors
                ],
            })
        else:
            result.execute.return_value = MagicMock(data=None)
        return result

    client.rpc.side_effect = _rpc
    return client


@pytest.fixture()
def vendor_selections() -> list[dict]:
    return [
        {"vendor_id": str(uuid4()), "vendor_contact_id": str(uuid4())},
    ]


@pytest.fixture()
def base_package_payload(vendor_selections) -> dict:
    """Payload as the router passes it to the service."""
    return {
        "task_id": str(TASK_ID),
        "bid_template_id": str(BID_TEMPLATE_ID),
        "deadline": _future_dt(),
        "project_document_ids": [],
        "vendor_selections": vendor_selections,
    }


@pytest.fixture(autouse=True)
def _patch_portal_url(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "PORTAL_BASE_URL", "https://portal.test", raising=False)
