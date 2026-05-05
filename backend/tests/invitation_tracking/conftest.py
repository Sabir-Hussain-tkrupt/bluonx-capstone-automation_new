"""
Shared fixtures for invitation tracking tests (Task 4.5).

Covers the read/status-management side of bid packages: detail view,
invitation list, PM-driven status updates, email log, and lazy expiration.

All Supabase operations are mocked via MagicMock chains simulating:
    db.table("name").select("...").eq("col", val).execute()
    db.table("name").update({...}).eq("col", val).execute()
    db.table("name").select("...").in_("col", [...]).execute()
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


# ── Deterministic IDs ──────────────────────────────────────────────────────

BID_PACKAGE_ID = uuid4()
TASK_ID = uuid4()
BID_TEMPLATE_ID = uuid4()
PM_USER_ID = uuid4()

# One invitation per status scenario so coverage is exhaustive.
INVITATION_STATUSES = ["sent", "opened", "submitted", "declined", "expired", "no_response"]
INVITATION_IDS = {status: uuid4() for status in INVITATION_STATUSES}

VENDOR_IDS = {status: uuid4() for status in INVITATION_STATUSES}
VENDOR_CONTACT_IDS = {status: uuid4() for status in INVITATION_STATUSES}

DOC_IDS = [uuid4() for _ in range(2)]
EMAIL_LOG_IDS = [uuid4() for _ in range(3)]

NONEXISTENT_BID_PACKAGE_ID = uuid4()
NONEXISTENT_INVITATION_ID = uuid4()


# ── Sample data ────────────────────────────────────────────────────────────


@pytest.fixture()
def future_deadline() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=14)


@pytest.fixture()
def past_deadline() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=2)


@pytest.fixture()
def sample_bid_template() -> dict:
    return {
        "id": str(BID_TEMPLATE_ID),
        "trade_id": str(uuid4()),
        "name": "Standard Grading Template",
        "is_lump_sum": True,
    }


@pytest.fixture()
def sample_task() -> dict:
    return {
        "id": str(TASK_ID),
        "name": "Rough Grading",
        "bid_type": "competitive",
        "status": "draft",
    }


@pytest.fixture()
def sample_bid_package_open(future_deadline, sample_task, sample_bid_template) -> dict:
    """Bid package that is open and has a future deadline (no lazy expiration)."""
    return {
        "id": str(BID_PACKAGE_ID),
        "task_id": str(TASK_ID),
        "round_number": 1,
        "deadline": future_deadline.isoformat(),
        "status": "open",
        "bid_template_id": str(BID_TEMPLATE_ID),
        "created_by": str(PM_USER_ID),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        # joined fields
        "tasks": {"name": sample_task["name"]},
        "bid_templates": sample_bid_template,
    }


@pytest.fixture()
def sample_bid_package_past_deadline(past_deadline, sample_task, sample_bid_template) -> dict:
    """Bid package still marked 'open' but deadline has passed — should expire lazily."""
    return {
        "id": str(BID_PACKAGE_ID),
        "task_id": str(TASK_ID),
        "round_number": 1,
        "deadline": past_deadline.isoformat(),
        "status": "open",
        "bid_template_id": str(BID_TEMPLATE_ID),
        "created_by": str(PM_USER_ID),
        "created_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        "updated_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        "tasks": {"name": sample_task["name"]},
        "bid_templates": sample_bid_template,
    }


@pytest.fixture()
def sample_bid_package_closed(past_deadline, sample_task, sample_bid_template) -> dict:
    return {
        "id": str(BID_PACKAGE_ID),
        "task_id": str(TASK_ID),
        "round_number": 1,
        "deadline": past_deadline.isoformat(),
        "status": "closed",
        "bid_template_id": str(BID_TEMPLATE_ID),
        "created_by": str(PM_USER_ID),
        "tasks": {"name": sample_task["name"]},
        "bid_templates": sample_bid_template,
    }


@pytest.fixture()
def sample_bid_package_cancelled(past_deadline, sample_task, sample_bid_template) -> dict:
    return {
        "id": str(BID_PACKAGE_ID),
        "task_id": str(TASK_ID),
        "round_number": 1,
        "deadline": past_deadline.isoformat(),
        "status": "cancelled",
        "bid_template_id": str(BID_TEMPLATE_ID),
        "created_by": str(PM_USER_ID),
        "tasks": {"name": sample_task["name"]},
        "bid_templates": sample_bid_template,
    }


def _make_invitation(status: str, sent_minutes_ago: int = 120) -> dict:
    now = datetime.now(timezone.utc)
    sent_at = (now - timedelta(minutes=sent_minutes_ago)).isoformat()
    opened_at = None
    responded_at = None
    if status in ("opened", "submitted", "declined"):
        opened_at = (now - timedelta(minutes=sent_minutes_ago - 10)).isoformat()
    if status in ("submitted", "declined"):
        responded_at = (now - timedelta(minutes=sent_minutes_ago - 20)).isoformat()

    return {
        "id": str(INVITATION_IDS[status]),
        "bid_package_id": str(BID_PACKAGE_ID),
        "vendor_id": str(VENDOR_IDS[status]),
        "vendor_contact_id": str(VENDOR_CONTACT_IDS[status]),
        "status": status,
        "sent_at": sent_at,
        "opened_at": opened_at,
        "responded_at": responded_at,
        "created_at": sent_at,
        "updated_at": sent_at,
        # joined fields
        "vendors": {
            "id": str(VENDOR_IDS[status]),
            "company_name": f"{status.title()} Vendor Co.",
        },
        "vendor_contacts": {
            "id": str(VENDOR_CONTACT_IDS[status]),
            "full_name": f"Contact {status.title()}",
            "email": f"{status}@example.com",
        },
    }


@pytest.fixture()
def sample_invitations_mixed_statuses() -> list[dict]:
    """Six invitations — one per possible status value."""
    return [_make_invitation(status) for status in INVITATION_STATUSES]


@pytest.fixture()
def sample_invitation_sent() -> dict:
    return _make_invitation("sent")


@pytest.fixture()
def sample_bid_package_documents() -> list[dict]:
    return [
        {
            "id": str(uuid4()),
            "bid_package_id": str(BID_PACKAGE_ID),
            "project_document_id": str(DOC_IDS[0]),
            "file_name": "grading_plan.pdf",
        },
        {
            "id": str(uuid4()),
            "bid_package_id": str(BID_PACKAGE_ID),
            "project_document_id": str(DOC_IDS[1]),
            "file_name": "site_survey.dwg",
        },
    ]


@pytest.fixture()
def sample_bid_submissions() -> list[dict]:
    """Two submitted bids; ordering is intentionally not pre-sorted so
    the service-layer sort can be exercised."""
    return [
        {"total_amount": 47500.00, "vendors": {"company_name": "Apex Grading"}},
        {"total_amount": 41200.00, "vendors": {"company_name": "Bedrock Civil"}},
    ]


@pytest.fixture()
def sample_email_log_rows() -> list[dict]:
    """Three email_log rows referencing invitations in the package."""
    now = datetime.now(timezone.utc)
    return [
        {
            "id": str(EMAIL_LOG_IDS[0]),
            "recipient_email": "sent@example.com",
            "recipient_type": "vendor_contact",
            "email_type": "bid_invitation",
            "subject": "New bid invitation: Rough Grading",
            "reference_type": "bid_invitations",
            "reference_id": str(INVITATION_IDS["sent"]),
            "status": "sent",
            "sent_at": (now - timedelta(hours=2)).isoformat(),
            "error_message": None,
            "created_at": (now - timedelta(hours=2)).isoformat(),
        },
        {
            "id": str(EMAIL_LOG_IDS[1]),
            "recipient_email": "opened@example.com",
            "recipient_type": "vendor_contact",
            "email_type": "bid_invitation",
            "subject": "New bid invitation: Rough Grading",
            "reference_type": "bid_invitations",
            "reference_id": str(INVITATION_IDS["opened"]),
            "status": "delivered",
            "sent_at": (now - timedelta(hours=2)).isoformat(),
            "error_message": None,
            "created_at": (now - timedelta(hours=2)).isoformat(),
        },
        {
            "id": str(EMAIL_LOG_IDS[2]),
            "recipient_email": "declined@example.com",
            "recipient_type": "vendor_contact",
            "email_type": "bid_invitation",
            "subject": "New bid invitation: Rough Grading",
            "reference_type": "bid_invitations",
            "reference_id": str(INVITATION_IDS["declined"]),
            "status": "failed",
            "sent_at": None,
            "error_message": "SMTP 550: mailbox not found",
            "created_at": (now - timedelta(hours=2)).isoformat(),
        },
    ]


# ── Mock Supabase ──────────────────────────────────────────────────────────


def build_chain(data=None):
    """
    Build a chain mock that accepts any combination of
        .select / .insert / .update / .delete
        .eq / .in_ / .is_ / .neq / .order / .limit / .single
    then .execute() returning data=<data or []>.
    """
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


@pytest.fixture()
def updates_captured() -> list[dict]:
    """Collects all payloads passed to .update() across all tables."""
    return []


@pytest.fixture()
def mock_supabase(
    sample_bid_package_open,
    sample_invitations_mixed_statuses,
    sample_email_log_rows,
    sample_bid_package_documents,
    sample_bid_submissions,
    updates_captured,
) -> MagicMock:
    """
    Table-aware mock Supabase client.

    Each call to .table(name) returns a fresh chain pre-loaded with the
    data the service is expected to read for that table. Writes are
    captured into `updates_captured`.
    """
    client = MagicMock()

    def table_side_effect(name: str):
        if name == "bid_packages":
            chain = build_chain(data=[sample_bid_package_open])
        elif name == "bid_invitations":
            chain = build_chain(data=sample_invitations_mixed_statuses)
        elif name == "email_log":
            chain = build_chain(data=sample_email_log_rows)
        elif name == "bid_package_documents":
            chain = build_chain(data=sample_bid_package_documents)
        elif name == "bid_submissions":
            chain = build_chain(data=sample_bid_submissions)
        else:
            chain = build_chain(data=[])

        # Capture writes — service may call .update(payload).eq(...).execute()
        # The side_effect returns `chain` directly (mirroring the
        # chain.update.return_value set up in build_chain) so subsequent
        # chaining like .eq(...).execute() still works.
        def capture(payload, _chain=chain, _name=name):
            updates_captured.append({"table": _name, "payload": payload})
            return _chain

        chain.update.side_effect = capture
        return chain

    client.table.side_effect = table_side_effect
    return client
