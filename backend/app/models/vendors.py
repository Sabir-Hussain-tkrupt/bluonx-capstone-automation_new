"""
Pydantic models for vendor-related tables:
  - vendors
  - vendor_contacts
  - vendor_trades
  - vendor_documents
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.models.common import BluOnXBase


# ── vendors ──────────────────────────────────────────────────────────────


class VendorCreate(BluOnXBase):
    company_name: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    insurance_expiration_date: date | None = None
    insurance_coverage_amount: Decimal | None = Field(default=None, ge=0)
    bonding_capacity: Decimal | None = Field(default=None, ge=0)
    max_active_jobs: int | None = Field(default=None, ge=0)
    onboarding_status: Literal["pending", "partial", "complete"] = "pending"
    status: Literal["active", "inactive", "suspended"] = "active"
    notes: str | None = None


class VendorUpdate(BluOnXBase):
    company_name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    insurance_expiration_date: date | None = None
    insurance_coverage_amount: Decimal | None = Field(default=None, ge=0)
    bonding_capacity: Decimal | None = Field(default=None, ge=0)
    max_active_jobs: int | None = Field(default=None, ge=0)
    onboarding_status: Literal["pending", "partial", "complete"] | None = None
    status: Literal["active", "inactive", "suspended"] | None = None
    notes: str | None = None


class VendorResponse(BluOnXBase):
    id: UUID
    company_name: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    insurance_expiration_date: date | None = None
    insurance_coverage_amount: Decimal | None = None
    bonding_capacity: Decimal | None = None
    max_active_jobs: int | None = None
    current_active_jobs: int
    onboarding_status: str
    status: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


# ── vendor_contacts ──────────────────────────────────────────────────────


class VendorContactCreate(BluOnXBase):
    vendor_id: UUID
    full_name: str
    email: str
    phone: str | None = None
    title: str | None = None
    is_primary: bool = False


class VendorContactUpdate(BluOnXBase):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    title: str | None = None
    is_primary: bool | None = None


class VendorContactResponse(BluOnXBase):
    id: UUID
    vendor_id: UUID
    full_name: str
    email: str
    phone: str | None = None
    title: str | None = None
    is_primary: bool
    created_at: datetime
    updated_at: datetime


# ── vendor_trades ────────────────────────────────────────────────────────


class VendorTradeCreate(BluOnXBase):
    vendor_id: UUID
    trade_id: UUID


class VendorTradeResponse(BluOnXBase):
    id: UUID
    vendor_id: UUID
    trade_id: UUID
    created_at: datetime


# ── vendor_documents ─────────────────────────────────────────────────────


class VendorDocumentCreate(BluOnXBase):
    vendor_id: UUID
    document_type: Literal["w9", "insurance_certificate", "master_trade_agreement"]
    file_name: str
    file_path: str
    file_size: int | None = None
    expiration_date: date | None = None
    status: Literal["valid", "expired", "pending_review"] = "valid"


class VendorDocumentResponse(BluOnXBase):
    id: UUID
    vendor_id: UUID
    document_type: str
    file_name: str
    file_path: str
    file_size: int | None = None
    expiration_date: date | None = None
    status: str
    uploaded_by: UUID
    uploaded_at: datetime
    updated_at: datetime
