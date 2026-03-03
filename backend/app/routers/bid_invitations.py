"""Bid invitation endpoints — /api/v1/bid-invitations"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.bids import (
    BidInvitationCreate,
    BidInvitationResponse,
    BidInvitationUpdate,
)

router = APIRouter()


@router.get("/bid-invitations", response_model=list[BidInvitationResponse])
async def list_bid_invitations(
    bid_package_id: UUID | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List bid invitations, optionally filtered by bid_package_id."""
    # TODO: Implement in later phase
    return []


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
