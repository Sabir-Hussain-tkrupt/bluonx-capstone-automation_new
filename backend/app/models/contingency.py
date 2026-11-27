"""Schemas for the contingency engine (Phase 3).

Money is `Decimal` end to end and leaves the API as a string, like the budget
models, so every amount stays exact to the cent.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from app.models.common import BluOnXBase


def _clean_text(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


def _clean_emails(v: list[str]) -> list[str]:
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
    default_field_approval_limit: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    contingency_near_zero_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    alert_escalation_days: int | None = Field(default=None, ge=1, le=60)
    alert_recipients: AlertRecipients | None = None
    # A number, or "off" for no executive approval level.
    executive_approval_threshold: Decimal | Literal["off"] | None = None
    land_team_emails: list[str] | None = None
    po_number_format: str | None = Field(default=None, min_length=1, max_length=40)
    po_number_format_contract: str | None = Field(default=None, min_length=1, max_length=40)
    quickbooks_expense_account: str | None = Field(default=None, min_length=1, max_length=100)
    bond_renewal_reminder_days: int | None = Field(default=None, ge=1, le=365)
    finance_emails: list[str] | None = None
    sales_emails: list[str] | None = None

    @field_validator("executive_approval_threshold")
    @classmethod
    def _threshold(cls, v):
        if isinstance(v, Decimal) and v < 0:
            raise ValueError("The executive threshold must be $0 or more")
        return v

    @field_validator("po_number_format", "po_number_format_contract")
    @classmethod
    def _po(cls, v: str | None) -> str | None:
        if v is not None and "{SEQ" not in v:
            raise ValueError("The PO format needs a {SEQ} or {SEQ:n} counter")
        return v

    @field_validator("finance_emails", "sales_emails", "land_team_emails")
    @classmethod
    def _emails(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _clean_emails(v)


class AlertRecipients(BluOnXBase):
    """Who hears about alerts of each severity, besides the project's managers."""

    warning: list[str] = []
    urgent: list[str] = []
    critical: list[str] = []

    @field_validator("warning", "urgent", "critical")
    @classmethod
    def _emails(cls, v: list[str]) -> list[str]:
        return _clean_emails(v)


ContingencySettingsUpdate.model_rebuild()
