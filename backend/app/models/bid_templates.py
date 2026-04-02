"""
Pydantic models for bid template management:
  - bid_templates
  - bid_template_items
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.models.common import BluOnXBase


# ── bid_template_items ──────────────────────────────────────────────────


class BidTemplateItemCreate(BluOnXBase):
    description: str = Field(..., min_length=1, max_length=255)
    item_type: Literal["lump_sum", "unit_price"]
    unit_of_measure: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def unit_required_for_unit_price(self):
        if self.item_type == "unit_price" and not self.unit_of_measure:
            raise ValueError(
                "unit_of_measure is required when item_type is 'unit_price'"
            )
        return self


class BidTemplateItemResponse(BluOnXBase):
    id: UUID
    bid_template_id: UUID
    description: str
    item_type: str
    unit_of_measure: str | None = None
    sort_order: int


# ── bid_templates ───────────────────────────────────────────────────────


class BidTemplateCreate(BluOnXBase):
    name: str = Field(..., min_length=1, max_length=255)
    trade_id: UUID | None = None
    is_lump_sum: bool = True
    items: list[BidTemplateItemCreate] = []

    @model_validator(mode="after")
    def items_required_for_structured(self):
        if not self.is_lump_sum and len(self.items) == 0:
            raise ValueError(
                "At least one line item is required when is_lump_sum is false"
            )
        return self


class BidTemplateUpdate(BluOnXBase):
    name: str = Field(..., min_length=1, max_length=255)
    trade_id: UUID | None = None
    is_lump_sum: bool = True
    items: list[BidTemplateItemCreate] = []

    @model_validator(mode="after")
    def items_required_for_structured(self):
        if not self.is_lump_sum and len(self.items) == 0:
            raise ValueError(
                "At least one line item is required when is_lump_sum is false"
            )
        return self


class BidTemplateResponse(BluOnXBase):
    id: UUID
    name: str
    trade_id: UUID | None = None
    is_lump_sum: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    trade_name: str | None = None
    item_count: int = 0


class BidTemplateDetailResponse(BidTemplateResponse):
    items: list[BidTemplateItemResponse] = []


class BidTemplateListResponse(BluOnXBase):
    """Paginated bid template list response."""
    items: list[BidTemplateResponse]
    total: int
    page: int
    page_size: int
