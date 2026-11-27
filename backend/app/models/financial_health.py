"""Schemas for contingency health and financial alerts (Phase 5)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.models.common import BluOnXBase


def _required(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("This field is required")
    return v


class HealthSetupUpdate(BluOnXBase):
    """Only the fields that are sent change. NULL clears."""

    manager_id: UUID | None = None
    field_manager_id: UUID | None = None
    reserve: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)


class AlertDecision(BluOnXBase):
    decision: Literal["proceed", "hold"]
    reason: str = Field(min_length=1, max_length=2000)
    discussed_with: UUID
    conversation_notes: str = Field(min_length=1, max_length=4000)

    _strip = field_validator("reason", "conversation_notes")(_required)


class HoldLift(BluOnXBase):
    reason: str = Field(min_length=1, max_length=2000)

    _strip = field_validator("reason")(_required)
