"""Schemas for escrows, property taxes and jurisdictions (Phase 7)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.common import BluOnXBase

Money = Field(ge=0, max_digits=15, decimal_places=2)


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class Installment(BluOnXBase):
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)


class JurisdictionSave(BluOnXBase):
    name: str = Field(min_length=1, max_length=150)
    kind: Literal["city", "county", "hoa", "other"] = "city"
    state: str | None = Field(default=None, max_length=50)
    repair_estimate_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    tax_installments: list[Installment] = Field(min_length=1, max_length=12)
    reminder_days_before: int = Field(default=30, ge=1, le=180)
    notes: str | None = Field(default=None, max_length=2000)

    _strip = field_validator("name", "state", "notes")(_clean)


class EscrowSave(BluOnXBase):
    name: str = Field(min_length=1, max_length=255)
    beneficiary: Literal["city", "county", "hoa", "other"]
    covered_areas: list[str] = Field(min_length=1, max_length=20)
    security_form: Literal["cash", "bond"]
    holder_type: Literal["insurance_company", "bank", "other"] | None = None
    holder_name: str | None = Field(default=None, max_length=255)
    secured_amount: Decimal = Money
    premium_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=15, decimal_places=2)
    premium_frequency: Literal["one_time", "yearly"] = "one_time"
    bond_number: str | None = Field(default=None, max_length=100)
    bond_expiry_date: date | None = None
    jurisdiction_id: UUID | None = None
    # NULL = the jurisdiction's repair % of the secured value.
    repair_estimate: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    expected_release_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)

    _strip = field_validator("name", "holder_name", "bond_number", "notes")(_clean)

    @field_validator("covered_areas")
    @classmethod
    def _areas(cls, v: list[str]) -> list[str]:
        out = [a.strip() for a in v if a and a.strip()]
        if not out:
            raise ValueError("List at least one area")
        return out


class EscrowTransition(BluOnXBase):
    to: Literal["posted", "works_built", "inspection", "corrections", "signed_off", "released", "cancelled"]
    on: date | None = None
    note: str | None = Field(default=None, max_length=4000)
    signoff_by: str | None = Field(default=None, max_length=255)

    _strip = field_validator("note", "signoff_by")(_clean)


class DefectSave(BluOnXBase):
    description: str = Field(min_length=1, max_length=2000)
    location: str | None = Field(default=None, max_length=255)
    repair_cost: Decimal = Money
    status: Literal["open", "repaired", "waived"] = "open"

    _strip = field_validator("description", "location")(_clean)


class BondRenewal(BluOnXBase):
    new_expiry_date: date
    premium: Decimal = Money


class TaxYearSave(BluOnXBase):
    tax_year: int = Field(ge=2000, le=2200)
    jurisdiction_id: UUID
    estimate_basis: Literal["prior_year_actual", "assessed_value", "manual"]
    amount: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    assessed_value: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    tax_rate_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=7, decimal_places=4)
    sold_portion_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    parcel_reference: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _basis(self):
        if self.estimate_basis == "manual" and self.amount is None:
            raise ValueError("Enter the estimated amount")
        if self.estimate_basis == "assessed_value" and (self.assessed_value is None or self.tax_rate_percent is None):
            raise ValueError("Enter the assessed value and the tax rate %")
        return self


class TaxUpdate(BluOnXBase):
    estimated_amount: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    actual_amount: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    due_date: date | None = None
    status: Literal["estimated", "billed", "sent_to_finance", "cancelled"] | None = None
    sold_portion_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)


class SoldPortion(BluOnXBase):
    percent: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    from_year: int | None = Field(default=None, ge=2000, le=2200)
