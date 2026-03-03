"""
Pydantic models for the trades table.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from app.models.common import BluOnXBase


class TradeCreate(BluOnXBase):
    name: str
    phase: Literal["due_diligence", "development", "both"]
    is_active: bool = True


class TradeUpdate(BluOnXBase):
    name: str | None = None
    phase: Literal["due_diligence", "development", "both"] | None = None
    is_active: bool | None = None


class TradeResponse(BluOnXBase):
    id: UUID
    name: str
    phase: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
