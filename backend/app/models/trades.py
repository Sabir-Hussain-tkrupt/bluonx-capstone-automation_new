"""
Pydantic models for the trades table.

A trade may have subtrades (one level: trade → subtrade). A subtrade has
`parent_trade_id` set and always carries its parent's phase (the database keeps
it in step), so `phase` is optional when creating one.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import field_validator, model_validator

from app.models.common import BluOnXBase

TradePhase = Literal["due_diligence", "development", "both"]


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Name is required")
    if len(cleaned) > 255:
        raise ValueError("Name must be 255 characters or fewer")
    return cleaned


class TradeCreate(BluOnXBase):
    name: str
    phase: TradePhase | None = None
    is_active: bool = True
    parent_trade_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return _clean_name(value)

    @model_validator(mode="after")
    def _phase_required_for_top_level(self) -> "TradeCreate":
        if self.parent_trade_id is None and self.phase is None:
            raise ValueError("Phase is required for a trade")
        return self


class TradeUpdate(BluOnXBase):
    name: str | None = None
    phase: TradePhase | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return _clean_name(value)


class TradeResponse(BluOnXBase):
    id: UUID
    name: str
    phase: str
    is_active: bool
    parent_trade_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class TradeUsage(BluOnXBase):
    """What references a trade. `in_use` blocks editing; `can_delete` also needs
    the trade to have no subtrades."""

    trade_id: UUID
    tasks: int = 0
    vendors: int = 0
    task_templates: int = 0
    bid_templates: int = 0
    budget_template_lines: int = 0
    variances: int = 0
    subtrades: int = 0
    total: int = 0
    in_use: bool = False
    can_edit: bool = True
    can_delete: bool = True
