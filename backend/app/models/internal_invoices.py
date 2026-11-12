"""Schemas for internal invoice intake (Phase 2 · Task 2.6)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.models.common import BluOnXBase


class InvoiceUpdate(BluOnXBase):
    """Edit invoice details while it is still `received` (not yet categorised)."""

    payee_name: str | None = Field(default=None, max_length=255)
    vendor_id: UUID | None = None
    invoice_number: str | None = Field(default=None, max_length=100)
    invoice_date: date | None = None
    amount: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    notes: str | None = None


class InvoiceCategorise(BluOnXBase):
    budget_line_id: UUID


class InvoiceResponse(BluOnXBase):
    id: UUID
    project_id: UUID
    budget_line_id: UUID | None = None
    vendor_id: UUID | None = None
    payee_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    amount: Decimal
    file_name: str
    file_size: int | None = None
    status: str
    notes: str | None = None
    uploaded_by: UUID
    created_at: datetime | None = None
    budget_line_name: str | None = None
    uploaded_by_name: str | None = None
    vendor_name: str | None = None


class CategoriseResult(BluOnXBase):
    invoice_id: UUID
    budget_line_id: UUID
    status: str
    allowance: Decimal
    overage: Decimal
    variance_id: UUID | None = None
    variance_line_id: UUID | None = None
    budget_status: str
    payment_approvals: list[dict]
