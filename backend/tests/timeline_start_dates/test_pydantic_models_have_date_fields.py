"""Task 8.1.5 — Pydantic schemas expose the new date fields.

These are cheap structural tests that pin the contract at the model
layer, independent of route wiring. They cover:
  - BidPackageCreateRequest accepts desired_start_date
  - BidPackageCreateResponse / BidPackageDetailResponse expose it
  - PortalBidPackageModel exposes desired_start_date
  - DraftPayload / BidDraftModel / SubmissionResponse expose proposed_start_date
  - RevisionPrefillResponse exposes proposed_start_date
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.models.bid_packages import (
    BidPackageCreateRequest,
    BidPackageCreateResponse,
    BidPackageDetailResponse,
    InvitationSummary,
)
from app.models.vendor_portal import (
    BidDraftModel,
    DraftPayload,
    PortalBidPackageModel,
    RevisionPrefillResponse,
    SubmissionResponse,
)


def test_bid_package_create_request_accepts_desired_start_date():
    req = BidPackageCreateRequest(
        deadline="2026-09-01T00:00:00+00:00",
        bid_template_id=uuid4(),
        vendor_selections=[
            {"vendor_id": uuid4(), "vendor_contact_id": uuid4()}
        ],
        desired_start_date="2026-10-01",
    )
    assert req.desired_start_date == date(2026, 10, 1)


def test_bid_package_create_request_desired_start_date_optional():
    req = BidPackageCreateRequest(
        deadline="2026-09-01T00:00:00+00:00",
        bid_template_id=uuid4(),
        vendor_selections=[
            {"vendor_id": uuid4(), "vendor_contact_id": uuid4()}
        ],
    )
    assert req.desired_start_date is None


def test_bid_package_create_response_serializes_desired_start_date():
    resp = BidPackageCreateResponse(
        bid_package_id=str(uuid4()),
        round_number=1,
        invitations_sent=1,
        invitations_failed=0,
        failed_vendors=[],
        deadline="2026-09-01T00:00:00+00:00",
        desired_start_date="2026-10-01",
    )
    assert "desired_start_date" in resp.model_dump()


def test_bid_package_detail_response_has_desired_start_date():
    resp = BidPackageDetailResponse(
        id=uuid4(),
        round_number=1,
        deadline="2026-09-01T00:00:00+00:00",
        status="open",
        invitation_summary=InvitationSummary(
            total=0, sent=0, opened=0, submitted=0,
            declined=0, expired=0, no_response=0,
        ),
        desired_start_date="2026-10-01",
    )
    assert resp.desired_start_date == date(2026, 10, 1)


def test_portal_bid_package_model_has_desired_start_date():
    m = PortalBidPackageModel(
        id=uuid4(),
        round_number=1,
        deadline="2026-09-01T00:00:00+00:00",
        instructions="",
        desired_start_date="2026-10-01",
    )
    assert m.desired_start_date == date(2026, 10, 1)


def test_draft_payload_accepts_proposed_start_date():
    p = DraftPayload(proposed_start_date="2026-10-05")
    assert p.proposed_start_date == date(2026, 10, 5)


def test_draft_payload_proposed_start_date_optional():
    p = DraftPayload()
    assert p.proposed_start_date is None


def test_bid_draft_model_has_proposed_start_date():
    m = BidDraftModel(
        id=uuid4(),
        vendor_notes="",
        line_items=[],
        attachment_ids=[],
        last_saved_at="2026-01-01T00:00:00+00:00",
        proposed_start_date="2026-10-05",
    )
    assert m.proposed_start_date == date(2026, 10, 5)


def test_submission_response_has_proposed_start_date():
    m = SubmissionResponse(
        id=uuid4(),
        status="draft",
        is_draft=True,
        vendor_notes="",
        updated_at="2026-01-01T00:00:00+00:00",
        line_items=[],
        attachments=[],
        proposed_start_date="2026-10-05",
    )
    assert m.proposed_start_date == date(2026, 10, 5)


def test_revision_prefill_response_has_proposed_start_date():
    m = RevisionPrefillResponse(
        vendor_notes="",
        line_items=[],
        attachment_ids=[],
        proposed_start_date="2026-10-05",
    )
    assert m.proposed_start_date == date(2026, 10, 5)
