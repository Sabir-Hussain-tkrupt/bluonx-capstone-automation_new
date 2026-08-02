"""Bid invitation endpoints — /api/v1/bid-invitations"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.bid_packages import (
    InvitationStatusUpdateRequest,
    InvitationUpdatedResponse,
    ResendBidLinkResponse,
)
from app.models.bids import (
    BidInvitationCreate,
    BidInvitationResponse,
    BidInvitationUpdate,
)
from app.services.bid_package_service import (
    BidPackageValidationError,
    resend_bid_link,
)
from app.services.invitation_tracking_service import (
    InvitationTrackingError,
    update_invitation_status,
)
from app.services.email_service import EmailService, get_email_service
from app.services.template_renderer import template_renderer

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/bid-invitations/{invitation_id}/resend-link",
    response_model=ResendBidLinkResponse,
    summary="Resend Bid Link",
)
async def resend_bid_link_endpoint(
    invitation_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
    email_service: EmailService = Depends(get_email_service),
):
    """Resend the bid link: hard-revoke all prior magic link tokens for
    this invitation, mint a new one, and email it to the vendor contact."""

    try:
        result = await resend_bid_link(
            invitation_id=invitation_id,
            current_user_id=UUID(user["user_id"]),
            db=db,
            email_service=email_service,
            template_renderer=template_renderer,
        )
    except BidPackageValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return result


@router.put(
    "/bid-invitations/{invitation_id}/status",
    response_model=InvitationUpdatedResponse,
)
async def update_invitation_status_endpoint(
    invitation_id: UUID,
    payload: InvitationStatusUpdateRequest,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """PM-driven status update. Only 'declined' and 'no_response' are allowed —
    system-managed statuses (and retired 'expired') return 400."""
    try:
        return await update_invitation_status(
            invitation_id=invitation_id,
            new_status=payload.status,
            current_user_id=UUID(user["user_id"]),
            db=db,
        )
    except InvitationTrackingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


# NOTE: no `GET /bid-invitations` list route by design. Invitations are read
# straight from Supabase under RLS, and the per-package view is served by
# `GET /bid-packages/{id}/invitations` in bid_packages.py. This was a stub
# returning `[]`, indistinguishable from an empty result.


@router.get("/bid-invitations/{invitation_id}", response_model=BidInvitationResponse)
async def get_bid_invitation(
    invitation_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single bid invitation by ID."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post(
    "/bid-invitations",
    response_model=BidInvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bid_invitation(
    invitation: BidInvitationCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a bid invitation for a vendor."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/bid-invitations/{invitation_id}", response_model=BidInvitationResponse)
async def update_bid_invitation(
    invitation_id: UUID,
    invitation: BidInvitationUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a bid invitation status."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/bid-invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bid_invitation(
    invitation_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Cancel a bid invitation."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")
