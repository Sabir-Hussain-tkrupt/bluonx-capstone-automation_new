"""
Pydantic models for the users table.

No UserCreate — users are created by the Supabase Auth trigger (fn_handle_new_auth_user),
not by the API directly. Admin invites go through auth.admin.invite_user_by_email, whose
metadata the trigger reads to populate the profile.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import EmailStr

from app.models.common import BluOnXBase


class UserInviteRequest(BluOnXBase):
    """Admin invite payload. `role` is constrained here so an invalid value is a
    422 that never reaches Supabase."""

    email: EmailStr
    full_name: str
    role: Literal["admin", "project_manager"]


class UserUpdate(BluOnXBase):
    full_name: str | None = None
    role: Literal["admin", "project_manager"] | None = None
    is_active: bool | None = None


class UserResponse(BluOnXBase):
    id: UUID
    email: str
    full_name: str
    role: Literal["admin", "project_manager"]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class UserAdminResponse(UserResponse):
    """Admin-list view: adds the derived account status and the inviting admin.

    `status` is computed in the service from is_active/deleted_at (public.users)
    and confirmed_at (Supabase auth):
      - deactivated: is_active is false OR the row is soft-deleted
      - pending:     invited but the auth user has not confirmed yet
      - active:      confirmed and not deactivated
    """

    status: Literal["active", "pending", "deactivated"]
    invited_by: UUID | None = None
