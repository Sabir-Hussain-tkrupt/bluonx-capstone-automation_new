"""
Pydantic models for the vendor portal API (Phase 5).

Field names and types mirror the frontend VendorBidContext interface
(frontend/src/features/vendor-portal/types/portal.ts) exactly, so the real
backend response is a drop-in replacement for the Task 5.1 mock.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.models.common import BluOnXBase


# ── Request ──────────────────────────────────────────────────────────────


class ValidateTokenRequest(BluOnXBase):
    token: str = Field(..., min_length=1, max_length=512)


# ── Response: nested context ─────────────────────────────────────────────


class PortalVendorModel(BluOnXBase):
    id: UUID
    company_name: str
    primary_contact_name: str
    email: str
    phone: str | None = None


class PortalProjectModel(BluOnXBase):
    id: UUID
    name: str
    location: str
    address: str


class PortalTaskModel(BluOnXBase):
    id: UUID
    name: str
    description: str
    trade_name: str


class PortalBidPackageModel(BluOnXBase):
    id: UUID
    round_number: int
    deadline: datetime
    instructions: str


class PortalTemplateItemModel(BluOnXBase):
    id: UUID
    description: str
    item_type: Literal["lump_sum", "unit_price"]
    unit_of_measure: str | None = None
    sort_order: int


class PortalBidTemplateModel(BluOnXBase):
    id: UUID
    name: str
    is_lump_sum: bool
    items: list[PortalTemplateItemModel]


class PortalProjectDocumentModel(BluOnXBase):
    id: UUID
    file_name: str
    file_size_bytes: int
    uploaded_at: datetime


class BidDraftLineItemModel(BluOnXBase):
    template_item_id: UUID
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    lump_sum_amount: Decimal | None = None


class BidDraftModel(BluOnXBase):
    id: UUID
    vendor_notes: str
    total_amount: Decimal | None = None
    line_items: list[BidDraftLineItemModel]
    attachment_ids: list[UUID]
    last_saved_at: datetime


class VendorBidContextModel(BluOnXBase):
    vendor: PortalVendorModel
    project: PortalProjectModel
    task: PortalTaskModel
    bid_package: PortalBidPackageModel
    bid_template: PortalBidTemplateModel
    project_documents: list[PortalProjectDocumentModel]
    existing_draft: BidDraftModel | None = None


class ValidateTokenResponse(BluOnXBase):
    jwt: str
    bid_context: VendorBidContextModel
