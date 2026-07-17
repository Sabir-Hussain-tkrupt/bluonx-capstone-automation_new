"""
Pydantic models for vendor_performance_reviews.

One PM rating (1-5) per completed contract. `contract_id`, `vendor_id`, and
`reviewed_by` are all resolved server-side and never trusted from the client:
the create endpoint takes only the rating and notes, and reads the contract id
from the path.
"""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.common import BluOnXBase


class ReviewCreate(BluOnXBase):
    """Create-review payload. rating is bounded at the model layer so an
    out-of-range value is rejected before the DB CHECK is ever reached."""

    rating: int = Field(ge=1, le=5)
    notes: str | None = None


class ReviewUpdate(BluOnXBase):
    """Edit an existing rating (fat-finger correction). Both optional so a caller
    can amend notes alone, but rating stays bounded when supplied."""

    rating: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None


class ReviewResponse(BluOnXBase):
    id: UUID
    contract_id: UUID
    vendor_id: UUID
    rating: int
    notes: str | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime
    created_at: datetime
    updated_at: datetime
