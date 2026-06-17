"""build_envelope_definition — pure, no network (Task 9.3b Part A)."""

import base64

from app.services.contract_pdf import OWNER_SIGN_ANCHOR, VENDOR_SIGN_ANCHOR
from app.services.docusign_client import build_envelope_definition

_PDF_B64 = base64.b64encode(b"%PDF-1.4 fake").decode("ascii")
_SOW_B64 = base64.b64encode(b"%PDF-1.4 sow").decode("ascii")


def _signers():
    return [
        {
            "name": "Jane Doe",
            "email": "jane@acme.com",
            "recipient_id": "1",
            "routing_order": "1",
            "anchor_string": VENDOR_SIGN_ANCHOR,
        },
        {
            "name": "BluOnX Signer",
            "email": "owner@bluonx.com",
            "recipient_id": "2",
            "routing_order": "2",
            "anchor_string": OWNER_SIGN_ANCHOR,
        },
    ]


def _one_doc():
    return [{"document_base64": _PDF_B64, "name": "Subcontract", "document_id": "1"}]


def test_two_sequential_signers_with_correct_routing():
    ed = build_envelope_definition(
        documents=_one_doc(),
        signers=_signers(),
        webhook_url="https://x/webhooks/docusign-connect",
    )
    signers = ed.recipients.signers
    assert len(signers) == 2
    vendor = next(s for s in signers if s.recipient_id == "1")
    owner = next(s for s in signers if s.recipient_id == "2")
    assert vendor.routing_order == "1"
    assert owner.routing_order == "2"


def test_signhere_anchor_tabs_present():
    ed = build_envelope_definition(
        documents=_one_doc(),
        signers=_signers(),
        webhook_url="https://x/webhooks/docusign-connect",
    )
    anchors = {
        s.recipient_id: s.tabs.sign_here_tabs[0].anchor_string
        for s in ed.recipients.signers
    }
    assert anchors["1"] == VENDOR_SIGN_ANCHOR
    assert anchors["2"] == OWNER_SIGN_ANCHOR


def test_envelope_status_sent_and_event_notification():
    ed = build_envelope_definition(
        documents=_one_doc(),
        signers=_signers(),
        webhook_url="https://hook.example/webhooks/docusign-connect",
    )
    assert ed.status == "sent"
    assert ed.event_notification is not None
    assert ed.event_notification.url == "https://hook.example/webhooks/docusign-connect"
    codes = {e.envelope_event_status_code for e in ed.event_notification.envelope_events}
    assert {"completed", "declined", "voided"} <= codes


def test_no_event_notification_when_url_absent():
    ed = build_envelope_definition(documents=_one_doc(), signers=_signers(), webhook_url=None)
    assert ed.event_notification is None


def test_contract_pdf_is_document_one_and_sow_exhibit_appended():
    docs = _one_doc() + [
        {"document_base64": _SOW_B64, "name": "Signed SOW", "document_id": "2"}
    ]
    ed = build_envelope_definition(
        documents=docs, signers=_signers(), webhook_url=None
    )
    assert len(ed.documents) == 2
    assert ed.documents[0].document_id == "1"
    assert ed.documents[0].document_base64 == _PDF_B64
    assert ed.documents[1].document_id == "2"
    assert ed.documents[1].document_base64 == _SOW_B64
