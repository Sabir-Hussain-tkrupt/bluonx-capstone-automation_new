"""Geocoding & proximity endpoints — /api/v1/projects/{id}/nearby-vendors"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.geocoding import NearbyVendorResponse
from app.services.distance import filter_vendors_by_distance

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/projects/{project_id}/nearby-vendors",
    response_model=list[NearbyVendorResponse],
)
async def get_nearby_vendors(
    project_id: UUID,
    trade_id: str | None = Query(default=None, description="Filter by trade ID"),
    radius: int = Query(default=75, ge=1, le=500, description="Radius in miles"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get vendors within a given radius of a project.

    Uses Haversine distance for filtering. Returns vendors sorted by
    distance ascending, each with a `distance_miles` field.
    """
    try:
        results = await filter_vendors_by_distance(
            db=db,
            project_id=str(project_id),
            trade_id=trade_id,
            radius_miles=radius,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Nearby vendors query failed for project %s: %s", project_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query nearby vendors",
        ) from exc

    return results
