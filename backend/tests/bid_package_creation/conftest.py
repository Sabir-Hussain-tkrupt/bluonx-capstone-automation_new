"""
Shared fixtures for bid package creation & invitation sending tests (Task 4.4).

All fixtures use function scope for test isolation. Database operations
are mocked via MagicMock chains simulating the Supabase client pattern:
    db.table("name").insert({...}).execute()
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.email_service import EmailSendResult


# ── IDs (deterministic UUIDs for readable assertions) ──────────────────────

PROJECT_ID = uuid4()
TASK_ID = uuid4()
TASK_INTERNAL_ID = uuid4()
TASK_COMPLETED_ID = uuid4()
TASK_CANCELLED_ID = uuid4()
BID_TEMPLATE_ID = uuid4()
PM_USER_ID = uuid4()

VENDOR_IDS = [uuid4() for _ in range(3)]
VENDOR_CONTACT_IDS = [uuid4() for _ in range(3)]
DOC_IDS = [uuid4() for _ in range(2)]

# IDs that will NOT exist in the mock DB
NONEXISTENT_TASK_ID = uuid4()
NONEXISTENT_TEMPLATE_ID = uuid4()
NONEXISTENT_VENDOR_ID = uuid4()
NONEXISTENT_CONTACT_ID = uuid4()
NONEXISTENT_DOC_ID = uuid4()
WRONG_PROJECT_DOC_ID = uuid4()
DELETED_TASK_ID = uuid4()
DELETED_VENDOR_ID = uuid4()
INACTIVE_VENDOR_ID = uuid4()
INACTIVE_VENDOR_CONTACT_ID = uuid4()
WRONG_VENDOR_CONTACT_ID = uuid4()  # belongs to a different vendor


# ── Sample data dicts ──────────────────────────────────────────────────────


@pytest.fixture()
def sample_project() -> dict:
    return {
        "id": str(PROJECT_ID),
        "name": "Sunrise Meadows Phase 2",
        "status": "active",
    }


@pytest.fixture()
def sample_task_competitive() -> dict:
    """A competitive task in draft status — valid for bid package creation."""
    return {
        "id": str(TASK_ID),
        "project_id": str(PROJECT_ID),
        "trade_id": str(uuid4()),
        "name": "Rough Grading",
        "phase": "development",
        "bid_type": "competitive",
        "status": "draft",
        "created_by": str(PM_USER_ID),
        "deleted_at": None,
    }


@pytest.fixture()
def sample_task_internal() -> dict:
    """An internal task — must be rejected for bid packages."""
    return {
        "id": str(TASK_INTERNAL_ID),
        "project_id": str(PROJECT_ID),
        "trade_id": str(uuid4()),
        "name": "Geotech Report (Internal)",
        "phase": "due_diligence",
        "bid_type": "internal",
        "status": "draft",
        "created_by": str(PM_USER_ID),
        "deleted_at": None,
    }


@pytest.fixture()
def sample_task_direct_assign() -> dict:
    """A legacy direct_assign task. The value is no longer creatable through the
    API, but the DB CHECK constraint still permits it, so the pipeline gate must
    turn an existing row away rather than let it enter the bid flow."""
    return {
        "id": str(TASK_INTERNAL_ID),
        "project_id": str(PROJECT_ID),
        "trade_id": str(uuid4()),
        "name": "Legacy Direct Assign Task",
        "phase": "development",
        "bid_type": "direct_assign",
        "status": "draft",
        "created_by": str(PM_USER_ID),
        "deleted_at": None,
    }


@pytest.fixture()
def sample_task_completed() -> dict:
    return {
        "id": str(TASK_COMPLETED_ID),
        "project_id": str(PROJECT_ID),
        "trade_id": str(uuid4()),
        "name": "Completed Task",
        "phase": "development",
        "bid_type": "competitive",
        "status": "completed",
        "created_by": str(PM_USER_ID),
        "deleted_at": None,
    }


@pytest.fixture()
def sample_task_cancelled() -> dict:
    return {
        "id": str(TASK_CANCELLED_ID),
        "project_id": str(PROJECT_ID),
        "trade_id": str(uuid4()),
        "name": "Cancelled Task",
        "phase": "development",
        "bid_type": "competitive",
        "status": "cancelled",
        "created_by": str(PM_USER_ID),
        "deleted_at": None,
    }


@pytest.fixture()
def sample_deleted_task() -> dict:
    return {
        "id": str(DELETED_TASK_ID),
        "project_id": str(PROJECT_ID),
        "trade_id": str(uuid4()),
        "name": "Deleted Task",
        "phase": "development",
        "bid_type": "competitive",
        "status": "draft",
        "created_by": str(PM_USER_ID),
        "deleted_at": "2025-01-01T00:00:00+00:00",
    }


@pytest.fixture()
def sample_bid_template() -> dict:
    return {
        "id": str(BID_TEMPLATE_ID),
        "trade_id": str(uuid4()),
        "name": "Standard Grading Template",
        "is_lump_sum": True,
        "created_by": str(PM_USER_ID),
    }


@pytest.fixture()
def sample_project_documents() -> list[dict]:
    return [
        {
            "id": str(DOC_IDS[0]),
            "project_id": str(PROJECT_ID),
            "file_name": "grading_plan.pdf",
            "file_path": f"{PROJECT_ID}/grading_plan.pdf",
            "file_type": "application/pdf",
            "file_size": 2_500_000,
            "uploaded_by": str(PM_USER_ID),
        },
        {
            "id": str(DOC_IDS[1]),
            "project_id": str(PROJECT_ID),
            "file_name": "site_survey.dwg",
            "file_path": f"{PROJECT_ID}/site_survey.dwg",
            "file_type": "application/acad",
            "file_size": 8_100_000,
            "uploaded_by": str(PM_USER_ID),
        },
    ]


@pytest.fixture()
def sample_vendors() -> list[dict]:
    """Three active vendors, each with a primary contact."""
    vendors = []
    names = [
        ("Smith Grading Co.", "John Smith", "john@smithgrading.com"),
        ("Apex Earthworks", "Maria Garcia", "maria@apexearth.com"),
        ("Summit Sitework", "David Chen", "david@summitsite.com"),
    ]
    for i, (company, contact_name, email) in enumerate(names):
        vendors.append({
            "vendor": {
                "id": str(VENDOR_IDS[i]),
                "company_name": company,
                "status": "active",
                "deleted_at": None,
            },
            "contact": {
                "id": str(VENDOR_CONTACT_IDS[i]),
                "vendor_id": str(VENDOR_IDS[i]),
                "full_name": contact_name,
                "email": email,
                "phone": f"555-000-{i:04d}",
                "is_primary": True,
            },
        })
    return vendors


@pytest.fixture()
def sample_pm_user() -> dict:
    return {
        "id": str(PM_USER_ID),
        "email": "pm@bluonx.dev",
        "full_name": "Alex Rivera",
        "role": "project_manager",
    }


@pytest.fixture()
def future_deadline() -> datetime:
    """A deadline 14 days in the future."""
    return datetime.now(timezone.utc) + timedelta(days=14)


@pytest.fixture()
def past_deadline() -> datetime:
    """A deadline in the past — should be rejected."""
    return datetime.now(timezone.utc) - timedelta(hours=1)


@pytest.fixture()
def vendor_selections() -> list[dict]:
    """The vendor_selections list sent in the request payload."""
    return [
        {"vendor_id": str(VENDOR_IDS[i]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[i])}
        for i in range(3)
    ]


@pytest.fixture()
def bid_package_request_payload(future_deadline, vendor_selections) -> dict:
    """Full request body for creating a bid package with invitations."""
    return {
        "task_id": str(TASK_ID),
        "bid_template_id": str(BID_TEMPLATE_ID),
        "deadline": future_deadline.isoformat(),
        "project_document_ids": [str(doc_id) for doc_id in DOC_IDS],
        "vendor_selections": vendor_selections,
    }


# ── Mock services ──────────────────────────────────────────────────────────


@pytest.fixture()
def mock_email_service() -> AsyncMock:
    """Mock EmailService that returns success for all sends by default."""
    service = AsyncMock()
    service.send_email.return_value = EmailSendResult(
        message_id=f"mock-{uuid4()}",
        status="sent",
        error=None,
    )
    return service


@pytest.fixture()
def mock_template_renderer() -> MagicMock:
    """Mock TemplateRenderer that returns placeholder HTML and text.

    Includes magic_link_url in output so token-extraction tests can find it.
    """
    renderer = MagicMock()

    def _render(template_name, context):
        url = context.get("magic_link_url", "")
        return f'<html><body>Bid Invitation <a href="{url}">{url}</a></body></html>'

    def _render_text(template_name, context):
        url = context.get("magic_link_url", "")
        return f"Bid Invitation (plain text) {url}"

    renderer.render.side_effect = _render
    renderer.render_text.side_effect = _render_text
    return renderer


def configure_create_rpc(
    mock_supabase: MagicMock,
    *,
    round_number: int = 1,
    bid_package_id: str | None = None,
) -> str:
    """Configure mock_supabase.rpc for fn_create_bid_package_with_invitations.

    The atomic creation now happens in a single RPC instead of per-row table
    inserts, so tests drive/inspect that call here. One invitation id is
    generated per vendor passed in p_vendors, mirroring the real function's
    {vendor_id, invitation_id} mapping. Returns the bid_package_id used.
    """
    bpid = str(bid_package_id or uuid4())

    def _side_effect(fn_name, params=None):
        result = MagicMock()
        if fn_name == "fn_create_bid_package_with_invitations":
            vendors = (params or {}).get("p_vendors", [])
            result.execute.return_value = MagicMock(data={
                "bid_package_id": bpid,
                "round_number": round_number,
                "invitations": [
                    {"vendor_id": v["vendor_id"], "invitation_id": str(uuid4())}
                    for v in vendors
                ],
            })
        else:
            result.execute.return_value = MagicMock(data=None)
        return result

    mock_supabase.rpc.side_effect = _side_effect
    return bpid


@pytest.fixture()
def mock_supabase() -> MagicMock:
    """
    Mock Supabase client with table chain + rpc support.

    Configures default return values for common operations. The atomic
    bid-package creation RPC is wired with a sensible default (round 1);
    individual tests can re-call configure_create_rpc to override.
    """
    client = MagicMock()

    def _make_chain(data=None):
        """Build a mock chain: .insert/.select/.update → .eq → .execute."""
        execute_mock = MagicMock()
        execute_mock.execute.return_value = MagicMock(data=data or [])

        chain = MagicMock()
        chain.insert.return_value = execute_mock
        chain.select.return_value = execute_mock
        chain.update.return_value = execute_mock
        chain.delete.return_value = execute_mock

        # Support .eq().execute() chaining
        execute_mock.eq.return_value = execute_mock
        execute_mock.is_.return_value = execute_mock
        execute_mock.single.return_value = execute_mock

        return chain

    client.table.return_value = _make_chain()
    configure_create_rpc(client)
    return client


# ── Portal URL ─────────────────────────────────────────────────────────────

PORTAL_BASE_URL = "https://portal.bluonx.com"


@pytest.fixture(autouse=True)
def _patch_portal_url(monkeypatch):
    """Ensure the service uses the test PORTAL_BASE_URL for all tests."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "PORTAL_BASE_URL", PORTAL_BASE_URL)
