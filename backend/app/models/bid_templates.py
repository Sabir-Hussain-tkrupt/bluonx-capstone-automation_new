"""
Pydantic models for bid template management:
  - bid_templates
  - bid_template_items
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.models.common import BluOnXBase


def _reject_items_on_lump_sum(is_lump_sum: bool, items: list) -> None:
    """Enforce the two-way is_lump_sum/items relationship.

    Structured (is_lump_sum=False) templates need at least one line item, or
    the vendor bid form renders nothing to price. Lump-sum templates must NOT
    carry items: the submit validator skips the line-item breakdown entirely
    for them (vendor_portal_submit_validator), so stored items would be dead
    data that the preview still renders — the two views of the same template
    would disagree.
    """
    if not is_lump_sum and len(items) == 0:
        raise ValueError(
            "At least one line item is required when is_lump_sum is false"
        )
    if is_lump_sum and len(items) > 0:
        raise ValueError(
            "A lump-sum template cannot have line items. "
            "Set is_lump_sum to false to use a line-item breakdown."
        )


# ── bid_template_items ──────────────────────────────────────────────────


class BidTemplateItemCreate(BluOnXBase):
    # Strip before validating so whitespace-only values fail min_length
    # instead of being stored blank. Without this, unit_of_measure="  " is
    # truthy and defeats unit_required_for_unit_price below.
    model_config = ConfigDict(str_strip_whitespace=True)

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
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255)
    trade_id: UUID | None = None
    is_lump_sum: bool = True
    items: list[BidTemplateItemCreate] = []

    @model_validator(mode="after")
    def items_match_bid_format(self):
        _reject_items_on_lump_sum(self.is_lump_sum, self.items)
        return self


class BidTemplateUpdate(BluOnXBase):
    """Full replace. Every field is required — omission is a 422, not a default.

    PUT rewrites the whole template, so a missing key used to mean "reset this":
    omitting trade_id silently cleared the trade association and omitting
    is_lump_sum silently forced lump-sum. One dropped field in a client payload
    could rewire a template with no error. Callers must now send all four.

    To clear the trade association, send trade_id explicitly as null.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255)
    trade_id: UUID | None = Field(...)
    is_lump_sum: bool = Field(...)
    items: list[BidTemplateItemCreate] = Field(...)

    @model_validator(mode="after")
    def items_match_bid_format(self):
        _reject_items_on_lump_sum(self.is_lump_sum, self.items)
        return self


class ReferencingPackageSummary(BluOnXBase):
    """Lightweight summary of a bid_package that references a template.

    Used to tell the PM exactly *which* package(s) lock a template, so
    the 409 message and the locked-state banner can name the blocker.
    """

    id: UUID
    task_name: str
    status: str


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
    is_in_use: bool = False


class BidTemplateDetailResponse(BidTemplateResponse):
    items: list[BidTemplateItemResponse] = []
    # Live (non-cancelled) packages locking this template. Capped server-side
    # at a small number so a heavily-used template doesn't ship thousands of
    # rows the UI never renders. Use `referencing_packages_total` for the
    # honest count when displaying "+N more" overflow.
    referencing_packages: list[ReferencingPackageSummary] = []
    referencing_packages_total: int = 0


class BidTemplateListResponse(BluOnXBase):
    """Paginated bid template list response."""
    items: list[BidTemplateResponse]
    total: int
    page: int
    page_size: int
