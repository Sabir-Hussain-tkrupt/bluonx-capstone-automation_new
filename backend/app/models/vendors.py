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

from pydantic import EmailStr, Field

from app.models.common import BluOnXBase


# ── vendors ──────────────────────────────────────────────────────────────


class VendorCreate(BluOnXBase):
    company_name: str = Field(..., min_length=2, max_length=255)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    zip_code: str | None = Field(default=None, max_length=20)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    insurance_expiration_date: date | None = None
    insurance_coverage_amount: Decimal | None = Field(default=None, ge=0)
    bonding_capacity: Decimal | None = Field(default=None, ge=0)
    max_active_jobs: int | None = Field(default=None, ge=0)
    onboarding_status: Literal["pending", "partial", "complete"] = "pending"
    status: Literal["active", "inactive", "suspended"] = "active"
    notes: str | None = None
    # Optional inline creation of contacts and trade associations
    contacts: list["VendorContactCreateInline"] | None = None
    trade_ids: list[UUID] | None = None


class VendorUpdate(BluOnXBase):
    company_name: str | None = Field(default=None, min_length=2, max_length=255)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    zip_code: str | None = Field(default=None, max_length=20)
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


class VendorDetailResponse(VendorResponse):
    """Extended vendor response with related entities for detail view."""
    contacts: list["VendorContactResponse"] = []
    trades: list["VendorTradeWithNameResponse"] = []
    documents: list["VendorDocumentResponse"] = []
    flags: list["VendorFlagResponse"] = []


class VendorListResponse(BluOnXBase):
    """Paginated vendor list response."""
    items: list[VendorResponse]
    total: int
    page: int
    page_size: int


# ── vendor_contacts ──────────────────────────────────────────────────────


class VendorContactCreateInline(BluOnXBase):
    """Contact creation when creating a vendor (no vendor_id needed)."""
    full_name: str
    email: EmailStr
    phone: str | None = None
    title: str | None = None
    is_primary: bool = False


class VendorContactCreate(BluOnXBase):
    vendor_id: UUID
    full_name: str
    email: EmailStr
    phone: str | None = None
    title: str | None = None
    is_primary: bool = False


class VendorContactUpdate(BluOnXBase):
    full_name: str | None = None
    email: EmailStr | None = None
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


class VendorBulkTradeCreate(BluOnXBase):
    """Bulk trade association — accepts multiple trade IDs at once."""
    trade_ids: list[UUID]


class VendorTradeResponse(BluOnXBase):
    id: UUID
    vendor_id: UUID
    trade_id: UUID
    created_at: datetime


class VendorTradeWithNameResponse(BluOnXBase):
    """Trade association with the trade name and phase included."""
    id: UUID
    vendor_id: UUID
    trade_id: UUID
    trade_name: str | None = None
    trade_phase: str | None = None
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


# ── vendor_flags ─────────────────────────────────────────────────────────


class VendorFlagResponse(BluOnXBase):
    id: UUID
    vendor_id: UUID
    flagged_by: UUID
    reason: str
    notes: str | None = None
    milestone_id: UUID | None = None
    is_resolved: bool
    resolved_at: datetime | None = None
    resolved_by: UUID | None = None
    created_at: datetime


# ── CSV Import ───────────────────────────────────────────────────────────


class VendorImportRow(BluOnXBase):
    """Single row from a CSV import."""
    company_name: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    contact_title: str | None = None
    notes: str | None = None


class VendorImportRequest(BluOnXBase):
    """Request body for bulk CSV import."""
    rows: list[VendorImportRow]


class VendorImportError(BluOnXBase):
    row: int
    message: str


class VendorImportResponse(BluOnXBase):
    """Response for CSV import operation."""
    created: int
    errors: list[VendorImportError]
