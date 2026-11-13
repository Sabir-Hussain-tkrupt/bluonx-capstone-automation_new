"""Schemas for project budgets, budget templates and land closings (Phase 2).

Money is `Decimal` end to end (never float) and leaves the API as a string, so
totals stay exact to the cent. Reads go straight to the v_budget_lines /
v_project_budget_summary views from the frontend; these models cover writes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.common import BluOnXBase

CashBucket = Literal["land", "vertical_construction", "overhead"]
LineSubtype = Literal[
    "land_purchase", "earnest_money", "due_diligence", "engineering",
    "escrow_bond_premium", "escrow_repairs", "property_tax", "other", "unallocated",
]
# Lines an admin may add by hand. Bid activities come from tasks; contingency is
# created with the budget; variances come from the variance procedures.
ManualLineType = Literal["land", "permit", "impact_fee", "soft_cost", "long_tail", "internal_tm"]
TemplateLineType = Literal[
    "land", "bid_activity", "internal_tm", "permit", "impact_fee", "soft_cost", "contingency", "long_tail",
]

Money = Decimal


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        raise ValueError("cannot be blank")
    return v


def _check_dates(start: date | None, end: date | None) -> None:
    if start and end and end < start:
        raise ValueError("The end date cannot be before the start date.")


def _check_money(v: Decimal | None) -> Decimal | None:
    if v is None:
        return None
    if v < 0:
        raise ValueError("Amounts cannot be negative.")
    if v.as_tuple().exponent < -2:
        raise ValueError("Amounts can have at most 2 decimal places.")
    return v


# ── Budget ──────────────────────────────────────────────────────────────────


class BudgetCreate(BluOnXBase):
    template_id: UUID | None = None
    contingency_percent: Decimal | None = Field(default=None, ge=0, le=100)


class BudgetLineCreate(BluOnXBase):
    line_type: ManualLineType
    line_subtype: LineSubtype | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    section_name: str | None = Field(default=None, max_length=100)
    parent_line_id: UUID | None = None
    budget_amount: Money = Decimal(0)
    anticipated_start_date: date | None = None
    anticipated_end_date: date | None = None
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    cash_bucket: CashBucket = "land"

    _clean_name = field_validator("name")(_clean)
    _money = field_validator("budget_amount")(_check_money)

    @model_validator(mode="after")
    def _dates(self) -> BudgetLineCreate:
        _check_dates(self.anticipated_start_date, self.anticipated_end_date)
        return self


class BudgetLineUpdate(BluOnXBase):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    section_name: str | None = Field(default=None, max_length=100)
    budget_amount: Money | None = None
    anticipated_start_date: date | None = None
    anticipated_end_date: date | None = None
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    cash_bucket: CashBucket | None = None

    _clean_name = field_validator("name")(_clean)
    _money = field_validator("budget_amount")(_check_money)

    @model_validator(mode="after")
    def _dates(self) -> BudgetLineUpdate:
        _check_dates(self.anticipated_start_date, self.anticipated_end_date)
        return self


class ReorderRequest(BluOnXBase):
    line_ids: list[UUID] = Field(min_length=1)


class BudgetLineResponse(BluOnXBase):
    id: UUID
    project_id: UUID
    task_id: UUID | None = None
    parent_line_id: UUID | None = None
    line_type: str
    line_subtype: str | None = None
    name: str
    section_name: str | None = None
    sort_order: int
    original_estimate: Decimal | None = None
    budget_amount: Decimal
    committed_amount: Decimal
    is_locked: bool
    anticipated_start_date: date | None = None
    anticipated_end_date: date | None = None
    payment_terms_days: int
    cash_bucket: str
    approval_state: str
    deleted_at: str | None = None


class SyncAwardsResult(BluOnXBase):
    applied: int
    locked: int
    failed: int


# ── Land closings ────────────────────────────────────────────────────────────


class LandClosingCreate(BluOnXBase):
    acres: Decimal | None = Field(default=None, ge=0)
    amount: Money
    planned_closing_date: date
    notes: str | None = None

    _money = field_validator("amount")(_check_money)


class LandClosingUpdate(BluOnXBase):
    acres: Decimal | None = Field(default=None, ge=0)
    amount: Money | None = None
    planned_closing_date: date | None = None
    actual_closing_date: date | None = None
    status: Literal["planned", "closed", "cancelled"] | None = None
    notes: str | None = None

    _money = field_validator("amount")(_check_money)


class LandClosingResponse(BluOnXBase):
    id: UUID
    project_id: UUID
    budget_line_id: UUID
    closing_sequence: int
    acres: Decimal | None = None
    amount: Decimal
    planned_closing_date: date
    actual_closing_date: date | None = None
    status: str
    notes: str | None = None


# ── Budget templates ─────────────────────────────────────────────────────────


class TemplateLineCreate(BluOnXBase):
    line_type: TemplateLineType
    line_subtype: LineSubtype | None = None
    name: str = Field(min_length=1, max_length=255)
    section_name: str | None = Field(default=None, max_length=100)
    trade_id: UUID | None = None
    default_amount: Money | None = None
    default_payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    default_cash_bucket: CashBucket | None = None

    _clean_name = field_validator("name")(_clean)
    _money = field_validator("default_amount")(_check_money)


class TemplateLineUpdate(BluOnXBase):
    line_subtype: LineSubtype | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    section_name: str | None = Field(default=None, max_length=100)
    trade_id: UUID | None = None
    default_amount: Money | None = None
    default_payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    default_cash_bucket: CashBucket | None = None
    is_active: bool | None = None

    _clean_name = field_validator("name")(_clean)
    _money = field_validator("default_amount")(_check_money)


class TemplateLineResponse(BluOnXBase):
    id: UUID
    budget_template_id: UUID
    line_type: str
    line_subtype: str | None = None
    name: str
    section_name: str | None = None
    trade_id: UUID | None = None
    sort_order: int
    default_amount: Decimal | None = None
    default_payment_terms_days: int | None = None
    default_cash_bucket: str | None = None
    is_active: bool
