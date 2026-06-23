"""
Pydantic v2 request/response models for bid package creation
and invitation sending (Task 4.4).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.models.common import BluOnXBase


class VendorSelection(BluOnXBase):
    """A single vendor + contact pair in a bid package creation request."""

    vendor_id: UUID
    vendor_contact_id: UUID


class BidPackageCreateRequest(BluOnXBase):
    """Request body for POST /v1/tasks/{task_id}/bid-packages."""

    deadline: datetime
    bid_template_id: UUID
    project_document_ids: list[UUID] = Field(default_factory=list)
    vendor_selections: list[VendorSelection] = Field(..., min_length=1)
    instructions: str | None = Field(default=None, max_length=2000)
    desired_start_date: date | None = None


class FailedVendor(BluOnXBase):
    """A vendor whose invitation email failed to send."""

    vendor_id: str
    error: str


class BidPackageCreateResponse(BluOnXBase):
    """Response body for bid package creation."""

    bid_package_id: str
    round_number: int
    invitations_sent: int
    invitations_failed: int
    failed_vendors: list[FailedVendor]
    deadline: str
    instructions: str | None = None
    desired_start_date: date | None = None


class ResendBidLinkResponse(BluOnXBase):
    """Response body for POST /v1/bid-invitations/{invitation_id}/resend-link."""

    invitation_id: str
    vendor_id: str
    new_token_generated: bool
    email_status: str


# ── Task 4.5: Invitation Tracking ────────────────────────────────────────


class InvitationSummary(BluOnXBase):
    """Per-status counts for invitations in a bid package."""

    total: int
    pending_send: int = 0
    sent: int
    send_failed: int = 0
    opened: int
    submitted: int
    declined: int
    expired: int
    no_response: int


class InvitationItem(BluOnXBase):
    """A single invitation row with vendor display fields."""

    id: UUID
    vendor_id: UUID | None = None
    vendor_company_name: str | None = None
    vendor_contact_name: str | None = None
    vendor_contact_email: str | None = None
    status: str
    sent_at: datetime | None = None
    opened_at: datetime | None = None
    responded_at: datetime | None = None
    bid_submission_id: UUID | None = None
    # True when the invitation's task has an active award (revision-blocking
    # statuses). Lets the PM UI hide "Request Revision" — the backend
    # create_revision_request guard remains the source of truth.
    is_awarded: bool = False


class ActiveAwardInfo(BluOnXBase):
    """The task's live award (status in pending_acceptance / accepted), if any.

    Lets the comparison UI mark the winning submission ("Pending signature" vs
    "Awarded ✓") and suppress the Award action on every row. Null when the task
    is re-awardable (no award, or only declined_by_vendor / cancelled)."""

    bid_submission_id: UUID | None = None
    status: str


class BidTemplateSummary(BluOnXBase):
    id: UUID
    name: str
    is_lump_sum: bool | None = None


class BidPackageDocumentItem(BluOnXBase):
    id: UUID
    file_name: str | None = None


class SubmittedBid(BluOnXBase):
    """A submitted bid (vendor company name + total amount) for chart display."""

    vendor_company_name: str
    total_amount: Decimal | None = None


class BidPackageDetailResponse(BluOnXBase):
    """Response for GET /v1/bid-packages/{bid_package_id}."""

    id: UUID
    task_name: str | None = None
    round_number: int
    deadline: datetime
    status: str
    instructions: str | None = None
    desired_start_date: date | None = None
    bid_template: BidTemplateSummary | None = None
    documents: list[BidPackageDocumentItem] = Field(default_factory=list)
    invitation_summary: InvitationSummary
    invitations: list[InvitationItem] = Field(default_factory=list)
    submitted_bids: list[SubmittedBid] = Field(default_factory=list)
    # The task's live award (or null when re-awardable). Drives the comparison
    # UI's Award-button suppression + winning-row "Awarded" state.
    award: ActiveAwardInfo | None = None


class InvitationListResponse(BluOnXBase):
    """Response for GET /v1/bid-packages/{bid_package_id}/invitations."""

    invitations: list[InvitationItem]


class InvitationStatusUpdateRequest(BluOnXBase):
    """Request body for PUT /v1/bid-invitations/{invitation_id}/status.

    Status is kept as a plain string here so the service layer can return
    a 400 with a descriptive detail message. The Pydantic layer only
    enforces that a value is provided.
    """

    status: str


class InvitationUpdatedResponse(BluOnXBase):
    """Response for PUT /v1/bid-invitations/{invitation_id}/status."""

    id: UUID
    bid_package_id: UUID | None = None
    vendor_id: UUID | None = None
    vendor_contact_id: UUID | None = None
    status: str
    sent_at: datetime | None = None
    opened_at: datetime | None = None
    responded_at: datetime | None = None
    updated_at: datetime | None = None


class EmailLogItem(BluOnXBase):
    id: UUID | None = None
    recipient_email: str | None = None
    email_type: str | None = None
    subject: str | None = None
    status: str | None = None
    sent_at: datetime | None = None
    error_message: str | None = None


class EmailLogResponse(BluOnXBase):
    """Response for GET /v1/bid-packages/{bid_package_id}/email-log."""

    items: list[EmailLogItem]


# ── Task 6.2: Cross-project bid package list ─────────────────────────────


class BidPackageListItem(BluOnXBase):
    """A single row in the cross-project bid package list view."""

    id: UUID
    task_id: UUID
    task_name: str
    project_id: UUID
    project_name: str
    round_number: int
    deadline: datetime
    status: str
    total_invitations: int
    submitted_count: int
    created_at: datetime


class BidPackageListResponse(BluOnXBase):
    """Response for GET /v1/bid-packages."""

    items: list[BidPackageListItem]
