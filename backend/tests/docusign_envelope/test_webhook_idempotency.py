"""Idempotency across Connect retries (Task 9.3b Part B).

Connect retries up to 5×/72h. A duplicate `completed` must be a no-op: no second
contract execute, no second award accept (no double capacity bump), no second
decline batch. The single guard is "stored terminal status == incoming".
"""

from uuid import uuid4

from app.routers.docusign_webhooks import handle_envelope_event

from .conftest import make_db

EID = str(uuid4())
CID = str(uuid4())
AID = str(uuid4())


def _env_row(status, award_status="pending_acceptance"):
    return {
        "id": EID,
        "status": status,
        "contract_id": CID,
        "contracts": {
            "id": CID,
            "status": "executed",
            "award_id": AID,
            "awards": {
                "id": AID,
                "status": award_status,
                "vendor_id": str(uuid4()),
                "task_id": str(uuid4()),
                "bid_submission_id": str(uuid4()),
                "bid_submissions": {"bid_invitations": {"bid_package_id": str(uuid4())}},
            },
        },
    }


async def test_duplicate_completed_is_noop(fake_email):
    # Envelope already stored as 'completed' — a retry must change nothing.
    calls: dict = {}
    db = make_db(
        {
            "docusign_envelopes": {"select": [_env_row("completed")], "default": [{}]},
            "contracts": {"default": [{}]},
            "awards": {"default": [{}]},
            "bid_invitations": {"select": []},
        },
        calls,
    )
    result = await handle_envelope_event(
        envelope_id="env-1", status="completed", payload={"dup": True},
        db=db, email_service=fake_email,
    )
    assert result == "noop"
    # No writes at all — not even the status/payload update.
    assert "contracts" not in calls
    assert "awards" not in calls
    assert calls.get("docusign_envelopes", {}).get("update") is None
    # No second decline batch.
    assert fake_email.sent == []


async def test_first_completed_then_duplicate(fake_email):
    """First completed applies; an immediately-following duplicate no-ops."""
    # First delivery — stored status is still 'sent'.
    calls1: dict = {}
    db1 = make_db(
        {
            "docusign_envelopes": {"select": [_env_row("sent")], "default": [{}]},
            "contracts": {"default": [{}]},
            "awards": {"default": [{}]},
            "bid_invitations": {"select": []},
        },
        calls1,
    )
    r1 = await handle_envelope_event(
        envelope_id="env-1", status="completed", payload={}, db=db1,
        email_service=fake_email,
    )
    assert r1 == "applied"
    assert calls1["awards"]["update"][0] == {"status": "accepted"}

    # Retry — now stored status is 'completed'.
    calls2: dict = {}
    db2 = make_db(
        {
            "docusign_envelopes": {"select": [_env_row("completed")], "default": [{}]},
            "contracts": {"default": [{}]},
            "awards": {"default": [{}]},
            "bid_invitations": {"select": []},
        },
        calls2,
    )
    r2 = await handle_envelope_event(
        envelope_id="env-1", status="completed", payload={}, db=db2,
        email_service=fake_email,
    )
    assert r2 == "noop"
    assert "awards" not in calls2
