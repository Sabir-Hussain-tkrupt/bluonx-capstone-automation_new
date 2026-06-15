"""Connect event → lifecycle transitions (Task 9.3b Part B).

handle_envelope_event is called directly with a recording mock DB so we can assert
the exact contract/award status writes and decline dispatch on each event.
"""

from uuid import uuid4

import pytest

from app.routers.docusign_webhooks import handle_envelope_event

from .conftest import make_db

EID = str(uuid4())
CID = str(uuid4())
AID = str(uuid4())
VID = str(uuid4())
TID = str(uuid4())
SID = str(uuid4())
PKG = str(uuid4())
ENVELOPE_ID = "env-abc-123"


def _env_row(status="sent"):
    return {
        "id": EID,
        "status": status,
        "contract_id": CID,
        "contracts": {
            "id": CID,
            "status": "sent_for_signature",
            "award_id": AID,
            "awards": {
                "id": AID,
                "status": "pending_acceptance",
                "vendor_id": VID,
                "task_id": TID,
                "bid_submission_id": SID,
                "bid_submissions": {"bid_invitations": {"bid_package_id": PKG}},
            },
        },
    }


def _other_invitation():
    return {
        "vendor_id": str(uuid4()),
        "vendor_contacts": {"full_name": "Bob Backup", "email": "bob@backup.com"},
        "bid_packages": {"tasks": {"name": "Grading", "projects": {"name": "Maple"}}},
    }


def _spec(env_status="sent", other_invites=None):
    return {
        "docusign_envelopes": {"select": [_env_row(env_status)], "default": [{}]},
        "contracts": {"default": [{}]},
        "awards": {"default": [{}]},
        "bid_invitations": {"select": other_invites if other_invites is not None else []},
    }


async def test_completed_executes_contract_accepts_award_and_declines(fake_email):
    calls: dict = {}
    db = make_db(_spec(other_invites=[_other_invitation()]), calls)
    result = await handle_envelope_event(
        envelope_id=ENVELOPE_ID, status="completed", payload={"x": 1},
        db=db, email_service=fake_email,
    )
    assert result == "applied"
    # Envelope row updated to completed + payload stored.
    env_update = calls["docusign_envelopes"]["update"][0]
    assert env_update["status"] == "completed"
    assert env_update["webhook_payload"] == {"x": 1}
    assert "completed_at" in env_update
    # Contract executed.
    assert calls["contracts"]["update"][0]["status"] == "executed"
    # Award accepted (fires +1 capacity trigger).
    assert calls["awards"]["update"][0] == {"status": "accepted"}
    # Declines fired to the backup pool.
    assert len(fake_email.sent) == 1
    assert fake_email.sent[0]["email_type"] == "decline_notification"


async def test_declined_terminates_contract_and_declines_award(fake_email):
    calls: dict = {}
    db = make_db(_spec(), calls)
    result = await handle_envelope_event(
        envelope_id=ENVELOPE_ID, status="declined", payload={}, db=db,
        email_service=fake_email,
    )
    assert result == "applied"
    assert calls["docusign_envelopes"]["update"][0]["status"] == "declined"
    assert calls["contracts"]["update"][0]["status"] == "terminated"
    assert calls["awards"]["update"][0] == {"status": "declined_by_vendor"}
    # No decline emails on a vendor decline.
    assert fake_email.sent == []


async def test_voided_terminates_contract_and_declines_award(fake_email):
    calls: dict = {}
    db = make_db(_spec(), calls)
    result = await handle_envelope_event(
        envelope_id=ENVELOPE_ID, status="voided", payload={}, db=db,
        email_service=fake_email,
    )
    assert result == "applied"
    assert calls["contracts"]["update"][0]["status"] == "terminated"
    assert calls["awards"]["update"][0] == {"status": "declined_by_vendor"}


async def test_delivered_updates_status_only(fake_email):
    calls: dict = {}
    db = make_db(_spec(), calls)
    result = await handle_envelope_event(
        envelope_id=ENVELOPE_ID, status="delivered", payload={}, db=db,
        email_service=fake_email,
    )
    assert result == "applied"
    assert calls["docusign_envelopes"]["update"][0]["status"] == "delivered"
    # No contract/award side effects on a non-terminal event.
    assert "contracts" not in calls
    assert "awards" not in calls


async def test_unknown_envelope_is_noop(fake_email):
    calls: dict = {}
    db = make_db({"docusign_envelopes": {"select": []}}, calls)
    result = await handle_envelope_event(
        envelope_id="nope", status="completed", payload={}, db=db,
        email_service=fake_email,
    )
    assert result == "unknown"
    assert "contracts" not in calls
    assert "awards" not in calls
