"""
Shared fixtures for PM bid submission detail tests (Task 6.2).

Mocks the Supabase client + the storage signed-URL helper, and overrides
the auth dependency so endpoint tests can use the FastAPI TestClient
without needing a real Supabase session.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.main import app


# ── Deterministic IDs ──────────────────────────────────────────────────────

SUBMISSION_ID = uuid4()
INVITATION_ID = uuid4()
VENDOR_ID = uuid4()
LINE_ITEM_IDS = [uuid4() for _ in range(3)]
ATTACHMENT_IDS = [uuid4() for _ in range(2)]
NONEXISTENT_SUBMISSION_ID = uuid4()


SIGNED_URL_TEMPLATE = "https://signed.example.com/{path}?token=abc"


# ── Sample data ────────────────────────────────────────────────────────────


@pytest.fixture()
def sample_submission_row() -> dict:
    """A full bid_submissions row with embedded vendor + invitation/contact."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(SUBMISSION_ID),
        "bid_invitation_id": str(INVITATION_ID),
        "status": "submitted",
        "is_direct_assign": False,
        "total_amount": "47500.00",
        "vendor_notes": "Includes mobilization and demobilization.",
        "submitted_at": now,
        "vendors": {"company_name": "Apex Grading"},
        "bid_invitations": {
            "vendor_contacts": {
                "full_name": "Jane Roe",
                "email": "jane@apex.example.com",
            }
        },
    }


@pytest.fixture()
def sample_direct_assign_row() -> dict:
    """A direct-assign submission (no real vendor portal flow)."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(SUBMISSION_ID),
        "bid_invitation_id": str(INVITATION_ID),
        "status": "submitted",
        "is_direct_assign": True,
        "total_amount": "82000.00",
        "vendor_notes": None,
        "submitted_at": now,
        "vendors": {"company_name": "Bedrock Civil"},
        "bid_invitations": {
            "vendor_contacts": {
                "full_name": "John Doe",
                "email": "john@bedrock.example.com",
            }
        },
    }


@pytest.fixture()
def sample_line_items_unordered() -> list[dict]:
    """Three line items returned out of sort_order on purpose."""
    return [
        {
            "id": str(LINE_ITEM_IDS[2]),
            "description": "Final grading",
            "item_type": "lump_sum",
            "quantity": None,
            "unit_of_measure": None,
            "unit_price": None,
            "lump_sum_amount": "5000.00",
            "line_total": "5000.00",
            "sort_order": 2,
        },
        {
            "id": str(LINE_ITEM_IDS[0]),
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
            "id": str(LINE_ITEM_IDS[1]),
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


@pytest.fixture()
def sample_attachments() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": str(ATTACHMENT_IDS[0]),
            "file_name": "scope.pdf",
            "file_path": f"{SUBMISSION_ID}/scope.pdf",
            "file_size": 12345,
            "file_type": "application/pdf",
            "uploaded_at": now,
        },
        {
            "id": str(ATTACHMENT_IDS[1]),
            "file_name": "schedule.xlsx",
            "file_path": f"{SUBMISSION_ID}/schedule.xlsx",
            "file_size": 6789,
            "file_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "uploaded_at": now,
        },
    ]


# ── Mock Supabase ──────────────────────────────────────────────────────────


def build_chain(data=None):
    chain = MagicMock()
    result = MagicMock()
    result.data = data if data is not None else []

    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.delete.return_value = chain
    chain.eq.return_value = chain
    chain.in_.return_value = chain
    chain.is_.return_value = chain
    chain.neq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.single.return_value = chain
    chain.maybe_single.return_value = chain
    chain.execute.return_value = result
    return chain


def _make_signed_url_storage_mock():
    """Stub out db.storage.from_(bucket).create_signed_url(path, ttl)."""
    storage = MagicMock()
    bucket = MagicMock()
    storage.from_.return_value = bucket

    def signed_url(path, _ttl):
        return {"signedURL": SIGNED_URL_TEMPLATE.format(path=path)}

    bucket.create_signed_url.side_effect = signed_url
    return storage


@pytest.fixture()
def mock_supabase(
    sample_submission_row, sample_line_items_unordered, sample_attachments
) -> MagicMock:
    client = MagicMock()

    def table_side_effect(name: str):
        if name == "bid_submissions":
            return build_chain(data=sample_submission_row)
        if name == "bid_line_items":
            return build_chain(data=sample_line_items_unordered)
        if name == "bid_attachments":
            return build_chain(data=sample_attachments)
        return build_chain(data=[])

    client.table.side_effect = table_side_effect
    client.storage = _make_signed_url_storage_mock()
    return client


@pytest.fixture()
def mock_supabase_direct_assign(
    sample_direct_assign_row, sample_line_items_unordered, sample_attachments
) -> MagicMock:
    client = MagicMock()

    def table_side_effect(name: str):
        if name == "bid_submissions":
            return build_chain(data=sample_direct_assign_row)
        if name == "bid_line_items":
            return build_chain(data=sample_line_items_unordered)
        if name == "bid_attachments":
            return build_chain(data=sample_attachments)
        return build_chain(data=[])

    client.table.side_effect = table_side_effect
    client.storage = _make_signed_url_storage_mock()
    return client


@pytest.fixture()
def sample_draft_submission_row(sample_submission_row) -> dict:
    """A still-draft submission (e.g. a revision in progress)."""
    row = dict(sample_submission_row)
    row["is_draft"] = True
    row["status"] = "draft"
    return row


@pytest.fixture()
def mock_supabase_draft(
    sample_draft_submission_row, sample_line_items_unordered, sample_attachments
) -> MagicMock:
    client = MagicMock()

    def table_side_effect(name: str):
        if name == "bid_submissions":
            return build_chain(data=sample_draft_submission_row)
        if name == "bid_line_items":
            return build_chain(data=sample_line_items_unordered)
        if name == "bid_attachments":
            return build_chain(data=sample_attachments)
        return build_chain(data=[])

    client.table.side_effect = table_side_effect
    client.storage = _make_signed_url_storage_mock()
    return client


@pytest.fixture()
def mock_supabase_not_found() -> MagicMock:
    client = MagicMock()

    def table_side_effect(name: str):
        return build_chain(data=None)

    client.table.side_effect = table_side_effect
    client.storage = _make_signed_url_storage_mock()
    return client


@pytest.fixture()
def mock_supabase_empty_extras(sample_submission_row) -> MagicMock:
    """Submission has no notes, no line items, no attachments."""
    sub = dict(sample_submission_row)
    sub["vendor_notes"] = None

    client = MagicMock()

    def table_side_effect(name: str):
        if name == "bid_submissions":
            return build_chain(data=sub)
        if name == "bid_line_items":
            return build_chain(data=[])
        if name == "bid_attachments":
            return build_chain(data=[])
        return build_chain(data=[])

    client.table.side_effect = table_side_effect
    client.storage = _make_signed_url_storage_mock()
    return client


# ── FastAPI TestClient with auth + db overrides ───────────────────────────


@pytest.fixture()
def authed_user() -> dict:
    return {
        "user_id": str(uuid4()),
        "email": "pm@example.com",
        "full_name": "PM User",
        "role": "project_manager",
        "is_active": True,
    }


@pytest.fixture()
def client_with_overrides(mock_supabase, authed_user):
    app.dependency_overrides[get_current_active_user] = lambda: authed_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client_direct_assign(mock_supabase_direct_assign, authed_user):
    app.dependency_overrides[get_current_active_user] = lambda: authed_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase_direct_assign
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client_not_found(mock_supabase_not_found, authed_user):
    app.dependency_overrides[get_current_active_user] = lambda: authed_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase_not_found
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client_empty_extras(mock_supabase_empty_extras, authed_user):
    app.dependency_overrides[get_current_active_user] = lambda: authed_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase_empty_extras
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client_no_auth(mock_supabase):
    """Client without auth override — requests without Bearer token must 401/403."""
    app.dependency_overrides[get_supabase] = lambda: mock_supabase
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
