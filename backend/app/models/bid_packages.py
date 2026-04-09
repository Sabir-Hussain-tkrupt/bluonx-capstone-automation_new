"""
Pydantic v2 request/response models for bid package creation
and invitation sending (Task 4.4).
"""

from __future__ import annotations

from datetime import datetime
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


class ResendInvitationResponse(BluOnXBase):
    """Response body for POST /v1/bid-invitations/{invitation_id}/resend."""

    invitation_id: str
    vendor_id: str
    new_token_generated: bool
    email_status: str
