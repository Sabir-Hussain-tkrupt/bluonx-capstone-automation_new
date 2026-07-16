"""
Pydantic models for the vendor portal API (Phase 5).

Field names and types mirror the frontend VendorBidContext interface
(frontend/src/features/vendor-portal/types/portal.ts) exactly, so the real
backend response is a drop-in replacement for the Task 5.1 mock.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.models.common import BluOnXBase


# ── Request ──────────────────────────────────────────────────────────────


class ValidateTokenRequest(BluOnXBase):
    token: str = Field(..., min_length=1, max_length=512)


class DeclineRevisionPayload(BluOnXBase):
    """Body for the SPA-mediated revision decline. The reason is optional —
    a blank textarea is normalized to NULL by the router before the write."""

    decline_reason: str | None = Field(None, max_length=500)


# ── Response: nested context ─────────────────────────────────────────────


class PortalVendorModel(BluOnXBase):
    id: UUID
    company_name: str
    primary_contact_name: str
    email: str
    phone: str | None = None


class PortalProjectModel(BluOnXBase):
    id: UUID
    name: str
    location: str
    address: str


class PortalTaskModel(BluOnXBase):
    id: UUID
    name: str
    description: str
    trade_name: str


class PortalBidPackageModel(BluOnXBase):
    id: UUID
    round_number: int
    deadline: datetime
    instructions: str
    desired_start_date: date | None = None
    # The PM-pinned Scope of Work the vendor must review and attest to.
    scope_of_work_document_id: UUID | None = None
    scope_of_work_file_name: str | None = None


class PortalTemplateItemModel(BluOnXBase):
    id: UUID
    description: str
    item_type: Literal["lump_sum", "unit_price"]
    unit_of_measure: str | None = None
    sort_order: int


class PortalBidTemplateModel(BluOnXBase):
    id: UUID
    name: str
    is_lump_sum: bool
    items: list[PortalTemplateItemModel]


class PortalProjectDocumentModel(BluOnXBase):
    id: UUID
    file_name: str
    file_size_bytes: int
    uploaded_at: datetime


class BidDraftLineItemModel(BluOnXBase):
    template_item_id: UUID
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    lump_sum_amount: Decimal | None = None


class BidDraftModel(BluOnXBase):
    id: UUID
    vendor_notes: str
    total_amount: Decimal | None = None
    line_items: list[BidDraftLineItemModel]
    attachment_ids: list[UUID]
    last_saved_at: datetime
    proposed_start_date: date | None = None
    sow_attested_name: str | None = None


class RevisionPrefillLineItem(BluOnXBase):
    template_item_id: UUID
    description: str
    item_type: Literal["lump_sum", "unit_price"]
    quantity: Decimal | None = None
    unit_of_measure: str | None = None
    unit_price: Decimal | None = None
    lump_sum_amount: Decimal | None = None
    line_total: Decimal
    sort_order: int


class RevisionPrefillResponse(BluOnXBase):
    """Original submission's data, shaped for the revision form prefill.

    Returned only by the revision-only prefill endpoint. attachment_ids
    are the original submission's bid_attachments; the SPA renders them
    read-only as "previously uploaded".
    """

    total_amount: Decimal | None = None
    vendor_notes: str
    line_items: list[RevisionPrefillLineItem]
    attachment_ids: list[UUID]
    proposed_start_date: date | None = None


class VendorRevisionContextModel(BluOnXBase):
    """Present only when the vendor entered via a revision magic link.

    Frontend checks `revision_context is not None` to render the
    "you are revising version N" banner.
    """

    bid_revision_request_id: UUID
    pm_note: str
    revision_deadline: datetime
    original_submission_id: UUID
    original_revision_number: int


class VendorBidContextModel(BluOnXBase):
    vendor: PortalVendorModel
    project: PortalProjectModel
    task: PortalTaskModel
    bid_package: PortalBidPackageModel
    bid_template: PortalBidTemplateModel
    project_documents: list[PortalProjectDocumentModel]
    existing_draft: BidDraftModel | None = None
    revision_context: VendorRevisionContextModel | None = None


class ValidateTokenResponse(BluOnXBase):
    jwt: str
    bid_context: VendorBidContextModel


# ── Request: draft create / update ───────────────────────────────────────


class DraftLineItemInput(BluOnXBase):
    """One line of vendor-entered pricing, keyed by template item."""

    template_item_id: UUID
    quantity: Decimal | None = Field(default=None, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    lump_sum_amount: Decimal | None = Field(default=None, ge=0)


class DraftPayload(BluOnXBase):
    """Body for POST /submissions and PUT /submissions/{id}.

    `attachment_ids` mirrors the frontend DraftPayload shape but the backend
    ignores it on write — attachments are owned exclusively by the
    upload/delete/list endpoints. Keeping the field here avoids a frontend
    type change and documents the contract.
    """

    vendor_notes: str = Field(default="", max_length=2000)
    total_amount: Decimal | None = Field(default=None, ge=0)
    line_items: list[DraftLineItemInput] = Field(default_factory=list)
    attachment_ids: list[UUID] = Field(default_factory=list)
    proposed_start_date: date | None = None
    # Vendor-typed CAPS company name attesting to the package Scope of Work.
    # Saved on the draft; required (unconditionally) at submit. Never prefilled
    # on a revision — the vendor re-types it each round.
    sow_attested_name: str | None = Field(default=None, max_length=255)


# ── Submit response ──────────────────────────────────────────────────────


class SubmitBidResponse(BluOnXBase):
    """Returned by POST /submissions/{id}/submit.

    Carries everything the confirmation page needs to render without a
    follow-up fetch: authoritative total + timestamp, plus the context
    fields needed for the "sent to {vendor_email}" notice. The email
    may fail to send even when the bid is committed — `confirmation_email_sent`
    reflects the actual provider result so the UI can soften the notice.
    """

    id: UUID
    submitted_at: datetime
    total_amount: Decimal | None = None
    vendor_email: str
    vendor_company_name: str
    project_name: str
    task_name: str
    attachment_count: int
    confirmation_email_sent: bool


# ── Submission detail (GET /submissions/{id}) ────────────────────────────


class SubmissionLineItemResponse(BluOnXBase):
    id: UUID
    description: str
    item_type: Literal["lump_sum", "unit_price"]
    quantity: Decimal | None = None
    unit_of_measure: str | None = None
    unit_price: Decimal | None = None
    lump_sum_amount: Decimal | None = None
    line_total: Decimal
    sort_order: int


class AttachmentResponse(BluOnXBase):
    id: UUID
    file_name: str
    file_size: int
    file_type: str | None = None
    uploaded_at: datetime


class SubmissionResponse(BluOnXBase):
    id: UUID
    status: Literal["draft", "submitted", "under_review", "accepted", "rejected"]
    is_draft: bool
    total_amount: Decimal | None = None
    vendor_notes: str
    submitted_at: datetime | None = None
    updated_at: datetime
    line_items: list[SubmissionLineItemResponse]
    attachments: list[AttachmentResponse]
    proposed_start_date: date | None = None


# ── Milestone check-in (Phase 10.2) ──────────────────────────────────────────
#
# A fully separate surface from the bid flow: milestone tokens live in their own
# table and their own validate endpoint. The vendor answers one Yes/No question
# derived from the check kind.

MilestoneCheckType = Literal["start", "progress", "completion"]


class MilestoneContextModel(BluOnXBase):
    """Everything the portal needs to render the one Yes/No check-in question.

    `check_type` selects the question ("Did this work start?" / "Will it finish
    by {end_date}?" / "Is this complete?"). `end_date` is the current working
    finish, shown in the progress question.
    """

    milestone_alert_id: UUID
    milestone_id: UUID
    milestone_name: str
    project_name: str
    task_name: str
    vendor_company_name: str
    check_type: MilestoneCheckType
    end_date: date
    cycle_number: int


class MilestoneValidateResponse(BluOnXBase):
    """Result of POST /vendor-auth/validate-milestone-token.

    Discriminated by `outcome`:
      - 'actionable'       → `jwt` + `milestone_context` present.
      - 'already_answered' → `recorded_value` + `recorded_at` present, no jwt.
    Stale / superseded / terminal check-ins are surfaced as a 410 error, not
    an outcome here.
    """

    outcome: Literal["actionable", "already_answered"]
    jwt: str | None = None
    milestone_context: MilestoneContextModel | None = None
    recorded_value: Literal["yes", "no"] | None = None
    recorded_at: datetime | None = None


class MilestoneRespondRequest(BluOnXBase):
    """Body for POST /vendor-portal/milestones/{milestone_alert_id}/respond.

    The answer is the ONLY thing the vendor supplies; identity comes from the
    milestone JWT, never the body.
    """

    value: Literal["yes", "no"]


class MilestoneRespondResponse(BluOnXBase):
    outcome: Literal["recorded", "already_answered"]
    recorded_value: Literal["yes", "no"]
    recorded_at: datetime
    milestone_status: str


# ── Validation error surface (422 on submit) ─────────────────────────────


class FieldError(BluOnXBase):
    field: str  # e.g. "line_items[2].unit_price" or "total_amount"
    message: str


class ValidationErrorResponse(BluOnXBase):
    detail: str = "Submission failed validation"
    errors: list[FieldError]


# ── Signed URL response (project doc download) ──────────────────────────


class SignedUrlResponse(BluOnXBase):
    url: str
    expires_in: int
