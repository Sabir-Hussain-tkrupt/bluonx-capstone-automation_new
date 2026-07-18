"""User endpoints — /api/v1/users"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user, require_admin
from app.core.supabase_client import get_supabase
from app.models.users import UserResponse, UserUpdate

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


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """List all users (admin only)."""
    # TODO: Implement in Phase 3
    return []


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Get a user by ID (admin only)."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Update a user (admin only)."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Soft-delete a user (admin only)."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")
