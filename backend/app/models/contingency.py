"""Schemas for the contingency engine (Phase 3).

Money is `Decimal` end to end and leaves the API as a string, like the budget
models, so every amount stays exact to the cent.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, field_validator

from app.models.common import BluOnXBase


def _clean_text(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class ContingencyPercentUpdate(BluOnXBase):
    """Project contingency %. NULL = the default from financial settings."""

    contingency_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)


class TopUpRequestCreate(BluOnXBase):
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("A top-up request needs a reason")
        return v


class TopUpDecision(BluOnXBase):
    approve: bool
    approved_amount: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=2)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        return _clean_text(v)


class BiddingCompleteRequest(BluOnXBase):
    note: str | None = Field(default=None, max_length=2000)
    # The checkpoint lists competitive / direct-assign tasks still without an
    # award; the project manager confirms them before completing.
    acknowledge_open_tasks: bool = False

    @field_validator("note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        return _clean_text(v)


class ContingencySettingsUpdate(BluOnXBase):
    default_contingency_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    bidding_target_contingency_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    bidding_escalation_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    finance_emails: list[str] | None = None
    sales_emails: list[str] | None = None

    @field_validator("finance_emails", "sales_emails")
    @classmethod
    def _emails(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        out: list[str] = []
        for raw in v:
            email = raw.strip()
            if not email:
                continue
            if "@" not in email or " " in email or len(email) > 254:
                raise ValueError(f"Not a valid email address: {email}")
            if email.lower() not in (e.lower() for e in out):
                out.append(email)
        return out
