"""User endpoints — /api/v1/users"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user, require_admin
from app.core.rate_limit import validate_token_rate_limit
from app.core.supabase_client import get_supabase
from app.models.common import MessageResponse
from app.models.users import (
    UserAdminResponse,
    UserInviteRequest,
    UserResponse,
    UserUpdate,
)
from app.services import user_service

router = APIRouter()


@router.get("/users/me", response_model=UserResponse)
async def get_current_user_profile(
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Return the authenticated user's full profile."""
    response = (
        db.table("users")
        .select("id, email, full_name, role, is_active, created_at, updated_at, deleted_at")
        .eq("id", user["user_id"])
        .maybe_single()
        .execute()
    )

    if not response or not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        )

    return response.data


@router.post(
    "/users/invite",
    response_model=UserAdminResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(validate_token_rate_limit)],
)
async def invite_user(
    payload: UserInviteRequest,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Invite a new admin/PM by email (admin only). Rate-limited: sends outbound email."""
    return user_service.invite_user(
        db,
        admin_id=user["user_id"],
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
    )


@router.get("/users", response_model=list[UserAdminResponse])
async def list_users(
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """List all users with derived account status (admin only)."""
    return user_service.list_users(db)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Get a user by ID (admin only)."""
    # Not part of the user-management surface; single-user reads are unused by the UI.
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/users/{user_id}", response_model=UserAdminResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Update a user's role / active state / name (admin only)."""
    return user_service.change_user(
        db, admin_id=user["user_id"], target_id=user_id, patch=payload
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Soft-delete a user (admin only)."""
    user_service.soft_delete_user(db, admin_id=user["user_id"], target_id=user_id)


@router.post("/users/{user_id}/restore", response_model=UserAdminResponse)
async def restore_user(
    user_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Restore a soft-deleted or deactivated user (admin only)."""
    return user_service.restore_user(
        db, admin_id=user["user_id"], target_id=user_id
    )


@router.post("/users/{user_id}/resend-invite", response_model=MessageResponse)
async def resend_invite(
    user_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Resend the invite email to a not-yet-confirmed user (admin only)."""
    return user_service.resend_invite(db, target_id=user_id)
