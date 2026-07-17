"""Vendor performance review endpoints — /api/v1/reviews

Create lives on the contract (`POST /contracts/{id}/review`) since a review is
born from a completed contract; this router owns the edit path. Reads are done by
the frontend directly against Supabase under RLS (no GET endpoint)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.reviews import ReviewResponse, ReviewUpdate
from app.services import review_service
from app.services.review_service import ReviewError

router = APIRouter()


@router.patch("/reviews/{review_id}", response_model=ReviewResponse)
async def update_review(
    review_id: UUID,
    review: ReviewUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Correct an existing rating. reviewed_at/reviewed_by advance to record who set
    the current rating; created_at stays frozen."""
    try:
        return review_service.update_review(
            review_id=str(review_id),
            # Only the fields the caller actually sent: an omitted field stays as-is,
            # an explicit null clears it (notes). Prevents a rating-only edit from
            # silently wiping the notes, and lets the PM clear notes on purpose.
            changes=review.model_dump(exclude_unset=True),
            reviewed_by=user["user_id"],
            db=db,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
