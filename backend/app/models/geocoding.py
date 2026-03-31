"""
Pydantic models for geocoding and nearby-vendors endpoints.
"""

from decimal import Decimal
from uuid import UUID

from app.models.common import BluOnXBase


class NearbyVendorResponse(BluOnXBase):
    """Vendor with distance from a project location."""

    id: UUID
    company_name: str
    city: str | None = None
    state: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    status: str
    distance_miles: float
