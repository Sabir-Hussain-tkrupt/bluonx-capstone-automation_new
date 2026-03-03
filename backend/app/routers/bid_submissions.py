"""Bid submission endpoints — /api/v1/bid-submissions"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.bids import (
    BidSubmissionCreate,
    BidSubmissionResponse,
    BidSubmissionUpdate,
)

router = APIRouter()


@router.get("/bid-submissions", response_model=list[BidSubmissionResponse])
async def list_bid_submissions(
    bid_package_id: UUID | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List bid submissions, optionally filtered by bid_package_id."""
    # TODO: Implement in later phase
    return []


@router.get("/bid-submissions/{submission_id}", response_model=BidSubmissionResponse)
async def get_bid_submission(
    submission_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single bid submission by ID."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post(
    "/bid-submissions",
    response_model=BidSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bid_submission(
    submission: BidSubmissionCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a bid submission."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/bid-submissions/{submission_id}", response_model=BidSubmissionResponse)
async def update_bid_submission(
    submission_id: UUID,
    submission: BidSubmissionUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a bid submission."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/bid-submissions/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bid_submission(
    submission_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a bid submission."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")
