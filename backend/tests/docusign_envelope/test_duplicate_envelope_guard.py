"""Duplicate-envelope guard for send_contract_envelope.

The `docusign_envelopes` insert happens AFTER create_envelope returns, so a crash
in between leaves a real envelope live at DocuSign with no local row — a state
locally indistinguishable from "never sent". Pressing "Send contract" there would
put a SECOND real contract in front of the vendor.

The guard asks DocuSign whether it already holds an envelope stamped with this
contract id (`bluonx_contract_id`, an envelope text custom field) and reconciles
instead of sending. It is skipped when the contract row was created in this very
call, since no envelope can reference a contract id that did not exist yet.

Fully offline: stub DocuSign client, fake email, mocked Supabase.
"""

from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.contract_envelope_service import (
    ContractEnvelopeError,
    _map_remote_status,
    send_contract_envelope,
)
from app.services.docusign_client import (
    ENVELOPE_CONTRACT_ID_FIELD,
    DocuSignClient,
    MockDocuSignAuthProvider,
    build_envelope_definition,
)

from .conftest import StubDocuSignClient, make_db

AID = str(uuid4())
VID = str(uuid4())
TID = str(uuid4())
SID = str(uuid4())
CID = str(uuid4())
SIGNER_ID = str(uuid4())

REMOTE_ENV_ID = "remote-env-already-live"


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
        "signer_id": SIGNER_ID,
        "contract_signers": {"full_name": "Dana Reyes", "email": "dana@bluonx.dev"},
        "bid_submissions": {
            "proposed_start_date": "2026-07-01",
            "sow_attested_at": "2026-06-15T10:00:00+00:00",
            "bid_invitations": {
                "vendor_contacts": {"full_name": "Jane Doe", "email": "jane@acme.com"}
            },
        },
        "vendors": {"company_name": "Acme Grading LLC"},
        "tasks": {
            "name": "Mass Grading",
            "project_id": str(uuid4()),
            "projects": {"name": "Maple Subdivision"},
        },
    }


def _contract_row():
    return {
        "id": CID,
        "award_id": AID,
        "contract_number": "CON-2026-ABCD1234",
        "status": "sent_for_signature",
        "payment_terms": None,
        "signer_name": None,
        "signer_email": None,
        "created_at": "2026-08-01T09:00:00+00:00",
    }


def _spec(*, contract_exists: bool, local_envelope=None, reconciled_row=None):
    """`contract_exists` False means create_contract_for_award INSERTs (created=True,
    lookup skipped); True means it reuses the existing row (created=False, lookup
    runs)."""
    contracts = (
        {"select": [_contract_row()]}
        if contract_exists
        else {"select": [], "insert": [_contract_row()]}
    )
    return {
        "awards": {"select": [_award_ctx()]},
        "contracts": contracts,
        "docusign_envelopes": {
            "select": [local_envelope] if local_envelope else [],
            "insert": [reconciled_row] if reconciled_row else [],
        },
        "bid_attachments": {"select": []},
    }


# ── The bad state: DocuSign holds an envelope we have no local row for ────────


async def test_remote_envelope_is_reconciled_without_a_second_send(
    fake_email, stub_client
):
    """A live remote envelope + no local row → write the local row from it and
    return it. The vendor must NOT receive a second contract."""
    stub_client.remote_envelope = {
        "envelope_id": REMOTE_ENV_ID,
        "status": "delivered",
        "sent_at": "2026-08-01T09:05:00+00:00",
    }
    calls: dict = {}
    db = make_db(_spec(contract_exists=True), calls)

    env = await send_contract_envelope(
        AID, db=db, client=stub_client, email_service=fake_email
    )

    # The lookup ran, and nothing was sent.
    assert stub_client.lookups == [CID]
    assert stub_client.sent_definitions == []
    # The local row was written from the remote envelope.
    env_insert = calls["docusign_envelopes"]["insert"][0]
    assert env_insert["envelope_id"] == REMOTE_ENV_ID
    assert env_insert["contract_id"] == CID
    assert env_insert["status"] == "delivered"
    assert env_insert["sent_at"] == "2026-08-01T09:05:00+00:00"
    assert env["envelope_id"] == REMOTE_ENV_ID
    # No award email either — the vendor was already emailed on the first send.
    assert fake_email.sent == []


async def test_remote_status_outside_the_check_constraint_maps_to_sent(
    fake_email, stub_client
):
    """docusign_envelopes.status is CHECK-constrained; DocuSign also returns
    `created`, which would violate it. It must be mapped, not copied."""
    stub_client.remote_envelope = {
        "envelope_id": REMOTE_ENV_ID,
        "status": "created",
        "sent_at": None,
    }
    calls: dict = {}
    db = make_db(_spec(contract_exists=True), calls)

    await send_contract_envelope(
        AID, db=db, client=stub_client, email_service=fake_email
    )

    assert calls["docusign_envelopes"]["insert"][0]["status"] == "sent"


def test_map_remote_status_allows_the_check_set_and_falls_back_otherwise():
    for allowed in ("sent", "delivered", "signed", "completed", "declined", "voided"):
        assert _map_remote_status(allowed) == allowed
    assert _map_remote_status("Delivered") == "delivered"  # DocuSign title-cases
    assert _map_remote_status("created") == "sent"
    assert _map_remote_status("something-new") == "sent"
    assert _map_remote_status(None) == "sent"


# ── Unknown state: a failed lookup must never fall through to a send ──────────


async def test_failed_lookup_raises_and_never_sends(fake_email, stub_client):
    """Fault tolerance is one-directional. A lookup that errors means unknown
    state, and sending on unknown state is the exact thing the guard prevents."""
    stub_client.remote_envelope = RuntimeError("DocuSign 503")
    db = make_db(_spec(contract_exists=True))

    with pytest.raises(ContractEnvelopeError) as exc_info:
        await send_contract_envelope(
            AID, db=db, client=stub_client, email_service=fake_email
        )

    assert exc_info.value.status_code == 502
    assert "Nothing was sent" in exc_info.value.detail
    assert stub_client.sent_definitions == []
    assert fake_email.sent == []


# ── Clean states: the guard gets out of the way ───────────────────────────────


async def test_nothing_local_nothing_remote_sends_normally(fake_email, stub_client):
    calls: dict = {}
    db = make_db(_spec(contract_exists=True), calls)

    await send_contract_envelope(
        AID, db=db, client=stub_client, email_service=fake_email
    )

    assert stub_client.lookups == [CID]
    assert len(stub_client.sent_definitions) == 1
    assert calls["docusign_envelopes"]["insert"][0]["envelope_id"] == "stub-env-123"


async def test_freshly_created_contract_skips_the_lookup(fake_email, stub_client):
    """The happy path. A contract row born in this call cannot have an envelope
    pointing at it, so the lookup would always come back empty — every normal
    award therefore makes zero extra DocuSign calls, and a list_status_changes
    outage cannot block a first-time send."""
    stub_client.remote_envelope = RuntimeError("must never be called")
    db = make_db(_spec(contract_exists=False))

    await send_contract_envelope(
        AID, db=db, client=stub_client, email_service=fake_email
    )

    assert stub_client.lookups == []
    assert len(stub_client.sent_definitions) == 1


# ── The join key that makes remote recognition possible ───────────────────────


def test_envelope_definition_carries_the_contract_id_custom_field():
    definition = build_envelope_definition(
        documents=[{"document_base64": "eA==", "name": "c.pdf", "document_id": "1"}],
        signers=[
            {
                "name": "Dana Reyes",
                "email": "dana@bluonx.dev",
                "recipient_id": "1",
                "routing_order": "1",
                "anchor_string": "/owner/",
            }
        ],
        contract_id=CID,
    )

    fields = definition.custom_fields.text_custom_fields
    assert len(fields) == 1
    assert fields[0].name == ENVELOPE_CONTRACT_ID_FIELD
    assert fields[0].value == CID
    # Our bookkeeping, not the signer's — never rendered to them.
    assert fields[0].show == "false"


def test_envelope_definition_omits_custom_fields_when_no_contract_id():
    definition = build_envelope_definition(
        documents=[{"document_base64": "eA==", "name": "c.pdf", "document_id": "1"}],
        signers=[
            {
                "name": "Dana Reyes",
                "email": "dana@bluonx.dev",
                "recipient_id": "1",
                "routing_order": "1",
                "anchor_string": "/owner/",
            }
        ],
    )

    assert definition.custom_fields is None


async def test_send_stamps_the_contract_id_on_the_real_definition(
    fake_email, stub_client
):
    db = make_db(_spec(contract_exists=False))

    await send_contract_envelope(
        AID, db=db, client=stub_client, email_service=fake_email
    )

    definition = stub_client.sent_definitions[0]
    field = definition.custom_fields.text_custom_fields[0]
    assert field.name == ENVELOPE_CONTRACT_ID_FIELD
    assert field.value == CID


# ── Mock provider: no account to search, so nothing to reconcile ──────────────


async def test_lookup_is_a_no_network_noop_under_mock_provider(monkeypatch):
    monkeypatch.setattr(settings, "DOCUSIGN_PROVIDER", "mock")
    client = DocuSignClient(provider=MockDocuSignAuthProvider())

    found = await client.find_envelope_by_contract_id(
        CID, from_date="2026-08-01T00:00:00+00:00"
    )

    assert found is None
