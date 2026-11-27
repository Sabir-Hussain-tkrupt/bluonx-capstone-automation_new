"""Schemas for payment approvals and the finance hand-off (Phase 6)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.common import BluOnXBase


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class PaymentRequest(BluOnXBase):
    payment_kind: Literal["full", "progress", "retainage_release"] = "full"
    progress_percent: Decimal | None = Field(default=None, gt=0, le=100, max_digits=5, decimal_places=2)
    note: str | None = Field(default=None, max_length=2000)
    # The field manager confirms the work is complete and approves in one go.
    confirm_work_complete: bool = False

    _note = field_validator("note")(_clean)

    @model_validator(mode="after")
    def _percent(self):
        if self.payment_kind == "progress" and self.progress_percent is None:
            raise ValueError("A progress payment needs a %")
        return self


class PaymentApprove(BluOnXBase):
    note: str | None = Field(default=None, max_length=2000)
    confirm_work_complete: bool = False

    _note = field_validator("note")(_clean)


class PaymentReject(BluOnXBase):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("A rejection needs a reason")
        return v


class PaymentNote(BluOnXBase):
    note: str | None = Field(default=None, max_length=2000)

    _note = field_validator("note")(_clean)


class ApproverSettingsUpdate(BluOnXBase):
    """Only the fields sent change. NULL clears (a NULL limit = the default)."""

    approval_limit: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    reports_to: UUID | None = None
    backup_approver_id: UUID | None = None
    away_until: datetime | None = None


class MarkExported(BluOnXBase):
    handoff_ids: list[UUID] = Field(min_length=1, max_length=1000)
