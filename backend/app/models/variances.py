"""Schemas for variance lines (Phase 4). Money is `Decimal`, like the budget models."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.common import BluOnXBase


def _required_text(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("cannot be blank")
    return v


class VarianceCreate(BluOnXBase):
    description: str = Field(min_length=1, max_length=2000)
    trade_id: UUID
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    # None = the vendor awarded on the parent line, when there is one.
    vendor_id: UUID | None = None

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str) -> str:
        return _required_text(v)


class VarianceUpdate(BluOnXBase):
    description: str | None = Field(default=None, max_length=2000)
    trade_id: UUID | None = None
    vendor_id: UUID | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=2)
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _not_null(self) -> "VarianceUpdate":
        for name in ("description", "amount", "trade_id"):
            value = getattr(self, name)
            if name in self.model_fields_set and (value is None or (isinstance(value, str) and not value.strip())):
                raise ValueError(f"{name} cannot be empty")
        return self


class VarianceNote(BluOnXBase):
    note: str | None = Field(default=None, max_length=2000)
    # Phase 6: the first approval confirms the work is complete.
    confirm_work_complete: bool = False


class VarianceReject(BluOnXBase):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        return _required_text(v)
