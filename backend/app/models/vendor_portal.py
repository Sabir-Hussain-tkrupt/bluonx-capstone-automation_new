"""
Pydantic models for the vendor portal API (Phase 5).

Field names and types mirror the frontend VendorBidContext interface
(frontend/src/features/vendor-portal/types/portal.ts) exactly, so the real
backend response is a drop-in replacement for the Task 5.1 mock.
"""

from __future__ import annotations

from datetime import datetime
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
