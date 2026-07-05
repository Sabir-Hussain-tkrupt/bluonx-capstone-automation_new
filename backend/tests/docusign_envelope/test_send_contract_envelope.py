"""send_contract_envelope orchestration + post-commit best-effort (Task 9.3b Part A).

Exercises the full send path offline (stub DocuSign client + fake email service):
contract row born in sent_for_signature, envelope persisted as sent, award email
sent. Plus: the award_service post-commit hook swallows a send failure so the award
is never rolled back.
"""

from uuid import uuid4

import pytest

from app.services.contract_envelope_service import (
    _compute_end_date,
    send_contract_envelope,
)
from app.services.contract_pdf import OWNER_SIGN_ANCHOR, VENDOR_SIGN_ANCHOR

from .conftest import make_db

AID = str(uuid4())
VID = str(uuid4())
TID = str(uuid4())
SID = str(uuid4())
CID = str(uuid4())
EID = str(uuid4())


def _award_ctx():
    return {
        "id": AID,
        "vendor_id": VID,
        "task_id": TID,
        "award_amount": "145000.00",
        "bid_submission_id": SID,
        "status": "pending_acceptance",
        "contract_valid_days": 365,
        "work_duration_days": 21,
        "bid_submissions": {
            "proposed_start_date": "2026-07-01",
            "bid_invitations": {
                "vendor_contacts": {"full_name": "Jane Doe", "email": "jane@acme.com"}
            },
        },
        "vendors": {"company_name": "Acme Grading LLC"},
        "tasks": {
            "name": "Mass Grading",
            "project_id": str(uuid4()),
            "projects": {"name": "Maple Subdivision", "estimated_end_date": "2026-12-31"},
        },
    }


def _contract_row():
    return {
        "id": CID,
        "award_id": AID,
        "contract_number": "CON-2026-ABCD1234",
        "status": "sent_for_signature",
        "payment_terms": None,
    }


def _env_row():
    return {"id": EID, "contract_id": CID, "envelope_id": "stub-env-123", "status": "sent"}


def _send_spec():
    return {
        "awards": {"select": [_award_ctx()]},
        "contracts": {"select": [], "insert": [_contract_row()]},
        "docusign_envelopes": {"select": [], "insert": [_env_row()]},
        "bid_attachments": {"select": []},
    }


async def test_send_creates_contract_persists_envelope_and_emails(fake_email, stub_client):
    calls: dict = {}
    db = make_db(_send_spec(), calls)
    env = await send_contract_envelope(
        AID, db=db, client=stub_client, email_service=fake_email
    )
    # Returned the persisted envelope row.
    assert env["envelope_id"] == "stub-env-123"
    # Contract born in sent_for_signature.
    contract_insert = calls["contracts"]["insert"][0]
    assert contract_insert["status"] == "sent_for_signature"
    assert contract_insert["award_id"] == AID
    assert contract_insert["contract_amount"] == "145000.00"
    assert contract_insert["start_date"] == "2026-07-01"
    # end_date is the task-scoped realization: proposed_start + work_duration_days
    # (21) — NOT the whole project's estimated_end_date (Task 9.8 bug fix).
    assert contract_insert["end_date"] == "2026-07-22"
    # Envelope persisted as sent, linked to the contract.
    env_insert = calls["docusign_envelopes"]["insert"][0]
    assert env_insert["status"] == "sent"
    assert env_insert["envelope_id"] == "stub-env-123"
    assert env_insert["contract_id"] == CID
    # The envelope was actually built + handed to the client.
    assert len(stub_client.sent_definitions) == 1
    # Award email sent to the invited contact.
    assert len(fake_email.sent) == 1
    assert fake_email.sent[0]["email_type"] == "award_notification"
    assert fake_email.sent[0]["to_email"] == "jane@acme.com"


async def test_resend_reuses_existing_envelope_no_double_send(fake_email, stub_client):
    """An envelope already on file for the contract → return it, don't re-send."""
    calls: dict = {}
    spec = _send_spec()
    spec["contracts"] = {"select": [_contract_row()]}  # contract already exists
    spec["docusign_envelopes"] = {"select": [_env_row()]}  # envelope already exists
    db = make_db(spec, calls)
    env = await send_contract_envelope(
        AID, db=db, client=stub_client, email_service=fake_email
    )
    assert env["envelope_id"] == "stub-env-123"
    # No new contract insert, no new envelope insert, no second send, no second email.
    assert "insert" not in calls.get("contracts", {})
    assert "insert" not in calls.get("docusign_envelopes", {})
    assert stub_client.sent_definitions == []
    assert fake_email.sent == []


async def test_post_commit_hook_swallows_send_failure(monkeypatch):
    """A DocuSign/PDF/email failure must NOT roll back the award (best-effort)."""
    from app.services import award_service

    async def _boom(*_a, **_k):
        raise RuntimeError("DocuSign down")

    # award_service imports send_contract_envelope locally from this module.
    monkeypatch.setattr(
        "app.services.contract_envelope_service.send_contract_envelope", _boom
    )

    inserted_award = {
        "id": AID, "task_id": TID, "bid_submission_id": SID, "vendor_id": VID,
        "status": "pending_acceptance", "award_amount": "50000.00",
    }
    spec = {
        "bid_submissions": {"select": [_clean_chain_row()]},
        # The award + task flip are written atomically via the fn_create_award
        # RPC (Task 9.2 / fix #1), which returns the inserted award row.
        "rpc": {"fn_create_award": [inserted_award]},
    }
    db = make_db(spec)
    result = await award_service.create_award(
        bid_submission_id=SID, has_override=False, override_justification=None,
        awarded_by=str(uuid4()), db=db,
    )
    # Award still returned despite the send blowing up.
    assert result["id"] == AID
    assert result["status"] == "pending_acceptance"


async def test_bluonx_signs_first_then_vendor(fake_email, stub_client):
    """Signing order: BluOnX (owner) is routingOrder 1, the vendor is 2. The
    anchor tab bound to each routing slot proves who signs when."""
    calls: dict = {}
    db = make_db(_send_spec(), calls)
    await send_contract_envelope(
        AID, db=db, client=stub_client, email_service=fake_email
    )
    ed = stub_client.sent_definitions[0]
    by_order = {
        s.routing_order: s.tabs.sign_here_tabs[0].anchor_string
        for s in ed.recipients.signers
    }
    assert by_order["1"] == OWNER_SIGN_ANCHOR  # BluOnX signs first
    assert by_order["2"] == VENDOR_SIGN_ANCHOR  # vendor countersigns


# ── end-date realization (Task 9.8 bug fix) ──────────────────────────────


def test_compute_end_date_both_present():
    """start + work_duration_days → an ISO date string."""
    assert _compute_end_date("2026-07-01", 21) == "2026-07-22"


def test_compute_end_date_null_start_returns_none():
    """No start → no computable end (relative phrasing takes over in the PDF)."""
    assert _compute_end_date(None, 21) is None
    assert _compute_end_date("", 21) is None


def test_compute_end_date_null_duration_returns_none():
    """No duration → no end date (must not fall back to the project end)."""
    assert _compute_end_date("2026-07-01", None) is None


def _clean_chain_row():
    """All-clean, awardable candidate on a closed package (mirrors awards tests)."""
    return {
        "total_amount": "50000.00",
        "proposed_start_date": None,
        "vendor_id": VID,
        "is_draft": False,
        "is_superseded": False,
        "status": "submitted",
        "is_direct_assign": False,
        "vendors": {
            "insurance_expiration_date": "2099-12-31",
            "bonding_capacity": "100000.00",
            "max_active_jobs": 10,
            "current_active_jobs": 1,
            "onboarding_status": "approved",
        },
        "bid_invitations": {
            "bid_packages": {
                "desired_start_date": None,
                "deadline": "2099-01-01",
                "status": "closed",
                "tasks": {
                    "id": TID,
                    "budget_estimate": "50000.00",
                    "project_id": str(uuid4()),
                    "projects": {"estimated_end_date": None},
                },
            },
        },
    }
