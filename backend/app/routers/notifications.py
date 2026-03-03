"""Notification endpoints — /api/v1/notifications"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.communications import NotificationCreate, NotificationResponse, NotificationUpdate

router = APIRouter()


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List notifications for the current user."""
    # TODO: Implement in later phase
    return []


@router.post(
    "/notifications",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification(
    notification: NotificationCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a notification."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/notifications/{notification_id}", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: UUID,
    notification: NotificationUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Mark a notification as read."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")
