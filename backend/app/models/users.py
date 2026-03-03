"""
Pydantic models for the users table.

No UserCreate — users are created by the Supabase Auth trigger (fn_handle_new_auth_user),
not by the API directly.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from app.models.common import BluOnXBase


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
