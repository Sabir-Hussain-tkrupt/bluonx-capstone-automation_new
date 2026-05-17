"""Award endpoints — /api/v1/awards"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.awards import AwardCreate, AwardResponse, AwardUpdate

router = APIRouter()


@router.get("/awards", response_model=list[AwardResponse])
async def list_awards(
    task_id: UUID | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List awards, optionally filtered by task_id."""
    # TODO: Implement in later phase
    return []


@router.get("/awards/{award_id}", response_model=AwardResponse)
async def get_award(
    award_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single award by ID."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/awards", response_model=AwardResponse, status_code=status.HTTP_201_CREATED)
async def create_award(
    award: AwardCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create an award for a bid submission."""
    # Fail fast BEFORE any (future) side effects: never award a
    # submission the vendor has since revised. The DB trigger
    # fn_enforce_award_consistency would only catch this with a cryptic
    # message; this gives the PM a clear, actionable error.
    sub_resp = (
        db.table("bid_submissions")
        .select("id, is_superseded")
        .eq("id", str(award.bid_submission_id))
        .limit(1)
        .execute()
    )
    sub_rows = sub_resp.data or []
    if sub_rows and sub_rows[0].get("is_superseded"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This submission has been revised. "
                "Award the latest version instead."
            ),
        )

    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/awards/{award_id}", response_model=AwardResponse)
async def update_award(
    award_id: UUID,
    award: AwardUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update an award (e.g., status change)."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/awards/{award_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_award(
    award_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Cancel an award."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")
