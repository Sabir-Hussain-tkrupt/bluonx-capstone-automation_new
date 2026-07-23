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

from pydantic import ConfigDict, EmailStr, Field, field_serializer

from app.models.common import BluOnXBase


# ── vendors ──────────────────────────────────────────────────────────────


class VendorCreate(BluOnXBase):
    # Strip before validating so a whitespace-only company_name fails
    # min_length instead of passing and being stored padded. Pydantic merges
    # this with BluOnXBase's config, so from_attributes still applies.
    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: str = Field(..., min_length=2, max_length=255)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    zip_code: str | None = Field(default=None, max_length=20)
    insurance_coverage_amount: Decimal | None = Field(default=None, ge=0)
    bonding_capacity: Decimal | None = Field(default=None, ge=0)
    max_active_jobs: int | None = Field(default=None, ge=0)
    # "complete" is deliberately absent here. It requires a valid insurance
    # certificate, and documents are stored under {vendor_id}/..., so none
    # can exist before this row does. Promote the vendor after uploading one.
    onboarding_status: Literal["pending", "partial"] = "pending"
    status: Literal["active", "inactive", "suspended"] = "active"
    notes: str | None = None
    # Optional inline creation of contacts and trade associations
    contacts: list["VendorContactCreateInline"] | None = None
    trade_ids: list[UUID] | None = None


class VendorUpdate(BluOnXBase):
    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: str | None = Field(default=None, min_length=2, max_length=255)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    zip_code: str | None = Field(default=None, max_length=20)
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
    #: Set only on create/update when geocoding could not refresh this row's
    #: coordinates. Null on reads. Non-fatal: the write succeeded, but the
    #: record will not take part in distance filtering until the address is
    #: fixed. Surfaced to the user as a warning toast.
    geocode_warning: str | None = None

    @field_serializer(
        "latitude",
        "longitude",
        "insurance_coverage_amount",
        "bonding_capacity",
    )
    def _decimal_as_number(self, value: Decimal | None) -> float | None:
        """Emit decimals as JSON numbers, matching PostgREST.

        Pydantic serializes Decimal to a string by default, but the frontend
        reads these same columns straight from PostgREST elsewhere, where a
        numeric comes back as a JSON number. Without this the same TypeScript
        type would describe two different runtime shapes depending on which
        path fetched the row.
        """
        return float(value) if value is not None else None


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

    model_config = ConfigDict(str_strip_whitespace=True)

    # min_length guards the now-stripped value: without it a whitespace-only
    # name would strip to "" and still validate.
    full_name: str = Field(..., min_length=1)
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
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str | None = Field(default=None, min_length=1)
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
    """Single row from a CSV import.

    Every field is optional at this layer so that a single malformed row
    (e.g. a missing company_name) does not fail Pydantic validation for the
    whole request. Per-row validation is performed by mapping each row to a
    VendorCreate in the import handler, which surfaces failures as row errors.
    """
    company_name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    contact_title: str | None = None
    notes: str | None = None


#: Maximum rows accepted in one import request.
#:
#: Each row costs a duplicate-name query, a Google geocode call (5s timeout),
#: a vendor insert and a contact insert, all sequential — roughly 0.4s per row,
#: or ~90s for a full batch when a tenth of the addresses fail to geocode.
#: Beyond this the request outlives any reasonable client timeout and the user
#: sees a failure while rows keep being created. Mirrored in the frontend
#: importer so oversized files are caught before upload.
VENDOR_IMPORT_MAX_ROWS = 100


class VendorImportRequest(BluOnXBase):
    """Request body for bulk CSV import."""
    rows: list[VendorImportRow] = Field(..., max_length=VENDOR_IMPORT_MAX_ROWS)


class VendorImportError(BluOnXBase):
    row: int
    message: str


class VendorImportResponse(BluOnXBase):
    """Response for CSV import operation."""
    created: int
    errors: list[VendorImportError]
