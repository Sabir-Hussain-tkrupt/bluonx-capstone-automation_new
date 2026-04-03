"""
Pydantic v2 models for the vendor filtering / qualified-vendors endpoint.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.models.common import BluOnXBase


class VendorPrimaryContact(BluOnXBase):
    """Primary contact info for a vendor."""

    id: UUID
    full_name: str
    email: str
    phone: str | None = None


class FilteredVendor(BluOnXBase):
    """A vendor returned by the filtering algorithm (qualified or disqualified)."""

    vendor_id: UUID
    company_name: str
    primary_contact: VendorPrimaryContact | None = None
    contact_warning: str | None = None
    distance_miles: float | None = None
    insurance_expiration_date: date | None = None
    insurance_days_remaining: int | None = None
    bonding_capacity: Decimal | None = None
    max_active_jobs: int | None = None
    current_active_jobs: int = 0
    available_capacity: int | None = None
    onboarding_status: str
    has_unresolved_flags: bool = False
    unresolved_flag_count: int = 0
    flag_reasons: list[str] = Field(default_factory=list)
    qualification_status: str  # "qualified" or "disqualified"
    disqualification_reasons: list[str] = Field(default_factory=list)


class FilterCriteria(BluOnXBase):
    """Criteria used by the filtering algorithm."""

    radius_miles: float
    trade_id: UUID
    trade_name: str | None = None
    min_bonding: Decimal | None = None
    insurance_cutoff_date: date


class QualifiedVendorsResponse(BluOnXBase):
    """Full response envelope for GET /tasks/{task_id}/qualified-vendors."""

    task_id: UUID
    task_name: str
    trade_name: str | None = None
    project_id: UUID
    project_name: str
    filter_criteria: FilterCriteria
    qualified_vendors: list[FilteredVendor] = Field(default_factory=list)
    disqualified_vendors: list[FilteredVendor] = Field(default_factory=list)
    total_qualified: int = 0
    total_disqualified: int = 0
    warnings: list[str] = Field(default_factory=list)
