"""
Pydantic models for bid lifecycle tables:
  - bid_templates, bid_template_items
  - bid_packages, bid_package_documents
  - bid_invitations
  - bid_submissions, bid_line_items, bid_attachments
  - bid_scores
  - magic_link_tokens (model only, no router)
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.models.common import BluOnXBase


# ── bid_templates ────────────────────────────────────────────────────────


class BidTemplateCreate(BluOnXBase):
    trade_id: UUID
    name: str
    is_lump_sum: bool = True


class BidTemplateUpdate(BluOnXBase):
    name: str | None = None
    is_lump_sum: bool | None = None


class BidTemplateResponse(BluOnXBase):
    id: UUID
    trade_id: UUID
    name: str
    is_lump_sum: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime


# ── bid_template_items ───────────────────────────────────────────────────


class BidTemplateItemCreate(BluOnXBase):
    bid_template_id: UUID
    description: str
    item_type: Literal["lump_sum", "unit_price"]
    unit_of_measure: str | None = None
    sort_order: int = 0


class BidTemplateItemResponse(BluOnXBase):
    id: UUID
    bid_template_id: UUID
    description: str
    item_type: str
    unit_of_measure: str | None = None
    sort_order: int


# ── bid_packages ─────────────────────────────────────────────────────────


class BidPackageCreate(BluOnXBase):
    task_id: UUID
    deadline: datetime
    # round_number is auto-set by DB trigger — not in Create schema


class BidPackageUpdate(BluOnXBase):
    deadline: datetime | None = None
    status: Literal["open", "closed", "evaluating", "cancelled"] | None = None


class BidPackageResponse(BluOnXBase):
    id: UUID
    task_id: UUID
    round_number: int
    deadline: datetime
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime


# ── bid_package_documents ────────────────────────────────────────────────


class BidPackageDocumentCreate(BluOnXBase):
    bid_package_id: UUID
    project_document_id: UUID


class BidPackageDocumentResponse(BluOnXBase):
    id: UUID
    bid_package_id: UUID
    project_document_id: UUID
    created_at: datetime


# ── bid_invitations ──────────────────────────────────────────────────────

BID_INVITATION_STATUSES = Literal[
    "sent", "opened", "submitted", "declined", "expired", "no_response",
]


class BidInvitationCreate(BluOnXBase):
    bid_package_id: UUID
    vendor_id: UUID
    vendor_contact_id: UUID


class BidInvitationUpdate(BluOnXBase):
    status: BID_INVITATION_STATUSES | None = None


class BidInvitationResponse(BluOnXBase):
    id: UUID
    bid_package_id: UUID
    vendor_id: UUID
    vendor_contact_id: UUID
    status: str
    sent_at: datetime | None = None
    opened_at: datetime | None = None
    responded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ── bid_submissions ──────────────────────────────────────────────────────

BID_SUBMISSION_STATUSES = Literal[
    "draft", "submitted", "under_review", "accepted", "rejected",
]


class BidSubmissionCreate(BluOnXBase):
    bid_invitation_id: UUID
    vendor_id: UUID  # denormalized, validated by DB trigger
    total_amount: Decimal | None = Field(default=None, ge=0)
    status: BID_SUBMISSION_STATUSES = "draft"
    is_draft: bool = True
    is_direct_assign: bool = False
    vendor_notes: str | None = None


class BidSubmissionUpdate(BluOnXBase):
    total_amount: Decimal | None = Field(default=None, ge=0)
    status: BID_SUBMISSION_STATUSES | None = None
    is_draft: bool | None = None
    vendor_notes: str | None = None


class BidSubmissionResponse(BluOnXBase):
    id: UUID
    bid_invitation_id: UUID
    vendor_id: UUID
    total_amount: Decimal | None = None
    status: str
    is_draft: bool
    is_direct_assign: bool
    submitted_at: datetime | None = None
    vendor_notes: str | None = None
    created_at: datetime
    updated_at: datetime


# ── bid_line_items ───────────────────────────────────────────────────────


class BidLineItemCreate(BluOnXBase):
    bid_submission_id: UUID
    description: str
    item_type: Literal["lump_sum", "unit_price"]
    quantity: Decimal | None = Field(default=None, ge=0)
    unit_of_measure: str | None = None
    unit_price: Decimal | None = Field(default=None, ge=0)
    lump_sum_amount: Decimal | None = Field(default=None, ge=0)
    line_total: Decimal = Field(ge=0)
    sort_order: int = 0


class BidLineItemResponse(BluOnXBase):
    id: UUID
    bid_submission_id: UUID
    description: str
    item_type: str
    quantity: Decimal | None = None
    unit_of_measure: str | None = None
    unit_price: Decimal | None = None
    lump_sum_amount: Decimal | None = None
    line_total: Decimal
    sort_order: int


# ── bid_attachments ──────────────────────────────────────────────────────


class BidAttachmentCreate(BluOnXBase):
    bid_submission_id: UUID
    file_name: str
    file_path: str
    file_type: str | None = None
    file_size: int | None = None


class BidAttachmentResponse(BluOnXBase):
    id: UUID
    bid_submission_id: UUID
    file_name: str
    file_path: str
    file_type: str | None = None
    file_size: int | None = None
    uploaded_at: datetime


# ── PM single bid detail view (Task 6.2) ────────────────────────────────


class PMBidLineItemResponse(BluOnXBase):
    id: UUID
    description: str
    item_type: Literal["lump_sum", "unit_price"]
    quantity: Decimal | None = None
    unit_of_measure: str | None = None
    unit_price: Decimal | None = None
    lump_sum_amount: Decimal | None = None
    line_total: Decimal
    sort_order: int


class PMBidAttachmentResponse(BluOnXBase):
    id: UUID
    file_name: str
    file_size: int
    file_type: str | None = None
    uploaded_at: datetime
    download_url: str
    download_url_expires_in: int


class PMBidSubmissionDetailResponse(BluOnXBase):
    id: UUID
    bid_invitation_id: UUID
    status: str
    is_direct_assign: bool
    is_superseded: bool = False
    supersedes_submission_id: UUID | None = None
    revision_number: int = 1
    total_amount: Decimal | None = None
    vendor_notes: str | None = None
    submitted_at: datetime | None = None
    vendor_company_name: str | None = None
    vendor_contact_name: str | None = None
    vendor_contact_email: str | None = None
    line_items: list[PMBidLineItemResponse]
    attachments: list[PMBidAttachmentResponse]


# ── bid_scores ───────────────────────────────────────────────────────────


class BidScoreCreate(BluOnXBase):
    bid_submission_id: UUID
    price_score: Decimal | None = Field(default=None, ge=0, le=100)
    compliance_score: Decimal | None = Field(default=None, ge=0, le=100)
    performance_score: Decimal | None = Field(default=None, ge=0, le=100)
    capacity_score: Decimal | None = Field(default=None, ge=0, le=100)
    timeline_score: Decimal | None = Field(default=None, ge=0, le=100)
    total_weighted_score: Decimal | None = Field(default=None, ge=0, le=100)
    scoring_metadata: dict | None = None


class BidScoreUpdate(BluOnXBase):
    price_score: Decimal | None = Field(default=None, ge=0, le=100)
    compliance_score: Decimal | None = Field(default=None, ge=0, le=100)
    performance_score: Decimal | None = Field(default=None, ge=0, le=100)
    capacity_score: Decimal | None = Field(default=None, ge=0, le=100)
    timeline_score: Decimal | None = Field(default=None, ge=0, le=100)
    total_weighted_score: Decimal | None = Field(default=None, ge=0, le=100)
    scoring_metadata: dict | None = None


class BidScoreResponse(BluOnXBase):
    id: UUID
    bid_submission_id: UUID
    price_score: Decimal | None = None
    compliance_score: Decimal | None = None
    performance_score: Decimal | None = None
    capacity_score: Decimal | None = None
    timeline_score: Decimal | None = None
    total_weighted_score: Decimal | None = None
    scoring_metadata: dict | None = None
    scored_at: datetime | None = None
    scored_by: UUID | None = None


# ── bid_revision_requests ────────────────────────────────────────────────

BID_REVISION_REQUEST_STATUSES = Literal[
    "pending", "submitted", "declined", "expired", "cancelled",
]


class BidRevisionRequestCreate(BluOnXBase):
    """PM-initiated request asking one vendor to revise a submitted bid.

    `original_submission_id` is NOT accepted from the client — it is derived
    server-side from the invitation's current (non-superseded, finalized)
    submission. `requested_by` comes from the authenticated PM.
    """

    bid_invitation_id: UUID
    pm_note: str = Field(..., min_length=1, max_length=2000)
    revision_deadline: datetime


class BidRevisionRequestResponse(BluOnXBase):
    id: UUID
    bid_invitation_id: UUID
    original_submission_id: UUID
    pm_note: str
    revision_deadline: datetime
    status: str
    decline_reason: str | None = None
    requested_by: UUID
    requested_at: datetime
    responded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BidRevisionRequestCreateResponse(BluOnXBase):
    """201 body for create. Carries the raw magic-link token + portal URL so
    the (later) email step can deliver it. The raw token is never persisted.
    """

    revision_request: BidRevisionRequestResponse
    magic_link_token: str
    portal_url: str


# ── magic_link_tokens (model only, no router) ───────────────────────────


class MagicLinkTokenResponse(BluOnXBase):
    id: UUID
    bid_invitation_id: UUID
    vendor_id: UUID
    token_hash: str
    expires_at: datetime
    used_at: datetime | None = None
    is_used: bool
    ip_address: str | None = None
    created_at: datetime
