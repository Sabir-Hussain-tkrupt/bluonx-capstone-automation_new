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
