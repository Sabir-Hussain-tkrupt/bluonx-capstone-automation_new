"""Milestone endpoints — /api/v1/milestones"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.milestones import (
    MilestoneCreate,
    MilestoneMarkCompleted,
    MilestoneMarkStarted,
    MilestoneReschedule,
    MilestoneResponse,
    MilestoneUpdate,
)
from app.services import milestone_service
from app.services.milestone_service import MilestoneError

router = APIRouter()


# ── Reads ───────────────────────────────────────────────────────────────
# The frontend reads milestones directly from Supabase under RLS (mirroring
# bid_packages), so these GET endpoints are intentionally left unimplemented.


@router.get("/milestones", response_model=list[MilestoneResponse])
async def list_milestones(
    contract_id: UUID | None = None,
    task_id: UUID | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List milestones — not exposed via API (frontend reads Supabase directly)."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/milestones/{milestone_id}", response_model=MilestoneResponse)
async def get_milestone(
    milestone_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single milestone — not exposed via API (frontend reads Supabase directly)."""
    raise HTTPException(status_code=501, detail="Not implemented")


# ── Writes ──────────────────────────────────────────────────────────────


@router.post("/milestones", response_model=MilestoneResponse, status_code=status.HTTP_201_CREATED)
async def create_milestone(
    milestone: MilestoneCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a milestone for the task's active contract."""
    try:
        return milestone_service.create_milestone(
            milestone, created_by=user["user_id"], db=db
        )
    except MilestoneError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.patch("/milestones/{milestone_id}", response_model=MilestoneResponse)
async def update_milestone(
    milestone_id: UUID,
    milestone: MilestoneUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a milestone's name, dates, notes, or sort order."""
    try:
        return milestone_service.update_milestone(str(milestone_id), milestone, db=db)
    except MilestoneError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.delete("/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_milestone(
    milestone_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a milestone (blocked once it has recorded activity)."""
    try:
        milestone_service.delete_milestone(str(milestone_id), db=db)
    except MilestoneError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/milestones/{milestone_id}/mark-started", response_model=MilestoneResponse)
async def mark_milestone_started(
    milestone_id: UUID,
    body: MilestoneMarkStarted,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Manual start override → in_progress."""
    try:
        return milestone_service.mark_started(
            str(milestone_id),
            actor_user_id=user["user_id"],
            actual_start_date=body.actual_start_date,
            db=db,
        )
    except MilestoneError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/milestones/{milestone_id}/mark-completed", response_model=MilestoneResponse)
async def mark_milestone_completed(
    milestone_id: UUID,
    body: MilestoneMarkCompleted,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Manual completion override → completed."""
    try:
        return milestone_service.mark_completed(
            str(milestone_id),
            actor_user_id=user["user_id"],
            actual_end_date=body.actual_end_date,
            db=db,
        )
    except MilestoneError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/milestones/{milestone_id}/reschedule", response_model=MilestoneResponse)
async def reschedule_milestone(
    milestone_id: UUID,
    body: MilestoneReschedule,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Push out the planned end date and return the milestone to in_progress."""
    try:
        return milestone_service.reschedule(
            str(milestone_id),
            actor_user_id=user["user_id"],
            end_date=body.end_date,
            db=db,
        )
    except MilestoneError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/milestones/{milestone_id}/cancel", response_model=MilestoneResponse)
async def cancel_milestone(
    milestone_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Cancel a milestone → cancelled. The correct way to retire a milestone that
    has activity (delete is blocked once history exists)."""
    try:
        return milestone_service.cancel_milestone(
            str(milestone_id), actor_user_id=user["user_id"], db=db
        )
    except MilestoneError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
