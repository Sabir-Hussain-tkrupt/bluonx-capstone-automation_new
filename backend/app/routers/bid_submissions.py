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
    PMBidSubmissionDetailResponse,
)
from app.services.bid_submission_detail_service import (
    BidSubmissionNotFoundError,
    get_pm_bid_submission_detail,
)

router = APIRouter()


# NOTE: no `GET /bid-submissions` list route by design. Submissions are read
# straight from Supabase under RLS, and the per-package cohort is served by
# `GET /bid-packages/{id}/invitations`. This was a stub returning `[]`, which a
# client could not tell apart from a package with no bids in yet.


@router.get(
    "/bid-submissions/{submission_id}",
    response_model=PMBidSubmissionDetailResponse,
)
async def get_bid_submission(
    submission_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single bid submission with vendor, line items, and attachments."""
    try:
        return await get_pm_bid_submission_detail(
            submission_id=submission_id, db=db
        )
    except BidSubmissionNotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


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
