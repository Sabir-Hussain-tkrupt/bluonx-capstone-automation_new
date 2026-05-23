"""In-app notification endpoints — /api/v1/notifications (Task 7.4).

The notifications table is owned by `NotificationService`; this router
only reads + flips `is_read`. FastAPI uses the Supabase service-role key,
which bypasses RLS — every query MUST include
`.eq("user_id", current_user["user_id"])` as the ownership gate.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.communications import (
    MarkAllReadResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.services.notification_service import build_notification_deep_link

router = APIRouter()


def _attach_deep_link(row: dict, db: Client) -> dict:
    row = dict(row)
    row["deep_link_path"] = build_notification_deep_link(row, db)
    return row


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Paginated list of the current user's notifications, newest first."""
    query = (
        db.table("notifications")
        .select("*")
        .eq("user_id", user["user_id"])
    )
    if unread_only:
        query = query.eq("is_read", False)
    resp = (
        query.order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    rows = resp.data or []
    return [_attach_deep_link(r, db) for r in rows]


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Count of unread notifications for the current user.

    Backed by the `idx_notifications_user_unread` partial index.
    """
    resp = (
        db.table("notifications")
        .select("id", count="exact")
        .eq("user_id", user["user_id"])
        .eq("is_read", False)
        .execute()
    )
    count = resp.count if resp.count is not None else len(resp.data or [])
    return {"count": count}


@router.patch(
    "/notifications/mark-all-read",
    response_model=MarkAllReadResponse,
)
async def mark_all_notifications_read(
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Bulk UPDATE — set is_read=TRUE on every unread row for this user."""
    resp = (
        db.table("notifications")
        .update({"is_read": True})
        .eq("user_id", user["user_id"])
        .eq("is_read", False)
        .execute()
    )
    return {"updated_count": len(resp.data or [])}


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
)
async def mark_notification_read(
    notification_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Mark a single notification as read.

    Ownership gate is the WHERE clause (`user_id = current_user`). If no
    row matches — either the id is wrong or it belongs to someone else —
    we return 404 without leaking which case it was.
    """
    resp = (
        db.table("notifications")
        .update({"is_read": True})
        .eq("id", str(notification_id))
        .eq("user_id", user["user_id"])
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return _attach_deep_link(rows[0], db)
