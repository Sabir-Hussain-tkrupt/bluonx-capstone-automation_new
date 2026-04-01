"""
Distance calculation and vendor filtering service.

Provides:
- Haversine formula (pure math, no API calls)
- Google Routes API distance (driving distance)
- Combined distance with Haversine fallback
- Vendor filtering by proximity to a project
"""

import logging
import math

import httpx
from supabase import Client

from app.core.config import settings

logger = logging.getLogger(__name__)

ROUTES_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
ROUTES_TIMEOUT = 10.0  # seconds
EARTH_RADIUS_MILES = 3958.8
METERS_PER_MILE = 1609.344


# ── Haversine Distance ─────────────────────────────────────────────────────


def haversine_distance(
    lat1: float | None,
    lng1: float | None,
    lat2: float | None,
    lng2: float | None,
) -> float | None:
    """Calculate straight-line distance in miles using the Haversine formula.

    Returns None if any coordinate is None.
    """
    if any(c is None for c in (lat1, lng1, lat2, lng2)):
        return None

    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_MILES * c


# ── Google Routes API Distance ──────────────────────────────────────────────


async def routes_api_distance(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> float | None:
    """Calculate driving distance via Google Routes API.

    Returns distance in miles, or None on any failure (caller should
    fall back to Haversine).
    """
    if not settings.GOOGLE_MAPS_API_KEY:
        return None

    body = {
        "origins": [
            {
                "waypoint": {
                    "location": {
                        "latLng": {"latitude": origin_lat, "longitude": origin_lng}
                    }
                }
            }
        ],
        "destinations": [
            {
                "waypoint": {
                    "location": {
                        "latLng": {"latitude": dest_lat, "longitude": dest_lng}
                    }
                }
            }
        ],
        "travelMode": "DRIVE",
    }

    headers = {
        "X-Goog-Api-Key": settings.GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "originIndex,destinationIndex,distanceMeters,condition",
    }

    try:
        async with httpx.AsyncClient(timeout=ROUTES_TIMEOUT) as client:
            response = await client.post(
                ROUTES_MATRIX_URL,
                json=body,
                headers=headers,
            )
            response.raise_for_status()

        data = response.json()

        # Response is a list of route matrix elements
        if not data or not isinstance(data, list):
            return None

        element = data[0]
        if element.get("condition") != "ROUTE_EXISTS":
            return None

        distance_meters = element.get("distanceMeters")
        if distance_meters is None:
            return None

        return distance_meters / METERS_PER_MILE

    except (httpx.HTTPError, httpx.TimeoutException, KeyError, IndexError, TypeError) as exc:
        logger.warning("Routes API distance failed: %s", exc)
        return None


# ── Combined Distance ───────────────────────────────────────────────────────


async def calculate_distance(
    lat1: float | None,
    lng1: float | None,
    lat2: float | None,
    lng2: float | None,
) -> float | None:
    """Calculate distance, preferring Routes API with Haversine fallback.

    Returns None if any coordinate is None.
    """
    if any(c is None for c in (lat1, lng1, lat2, lng2)):
        return None

    # Try Routes API first (driving distance)
    result = await routes_api_distance(lat1, lng1, lat2, lng2)
    if result is not None:
        return result

    # Fallback to Haversine (straight-line)
    return haversine_distance(lat1, lng1, lat2, lng2)


# ── Vendor Filtering by Distance ────────────────────────────────────────────


async def filter_vendors_by_distance(
    db: Client,
    project_id: str,
    trade_id: str | None = None,
    radius_miles: float = 75,
) -> list[dict]:
    """Filter vendors by proximity to a project.

    Steps:
    1. Fetch project coords — raise ValueError if missing.
    2. Fetch active vendors (optionally filtered by trade).
    3. Haversine pre-filter at radius * 1.33 for generous buffer.
    4. Return sorted by distance ascending, each with distance_miles.
    """
    # 1. Get project coordinates
    project_resp = (
        db.table("projects")
        .select("id, latitude, longitude")
        .eq("id", project_id)
        .is_("deleted_at", "null")
        .single()
        .execute()
    )

    if not project_resp.data:
        raise ValueError("Project not found")

    project = project_resp.data
    proj_lat = float(project["latitude"]) if project.get("latitude") else None
    proj_lng = float(project["longitude"]) if project.get("longitude") else None

    if proj_lat is None or proj_lng is None:
        raise ValueError("Project has no geocoded coordinates")

    # 2. Fetch vendors
    if trade_id:
        # Get vendor IDs with the specified trade
        trade_resp = (
            db.table("vendor_trades")
            .select("vendor_id")
            .eq("trade_id", trade_id)
            .execute()
        )
        vendor_ids = [r["vendor_id"] for r in (trade_resp.data or [])]
        if not vendor_ids:
            return []

        vendor_query = (
            db.table("vendors")
            .select("id, company_name, city, state, latitude, longitude, status")
            .is_("deleted_at", "null")
            .not_.is_("latitude", "null")
            .in_("id", vendor_ids)
        )
    else:
        vendor_query = (
            db.table("vendors")
            .select("id, company_name, city, state, latitude, longitude, status")
            .is_("deleted_at", "null")
            .not_.is_("latitude", "null")
        )

    vendor_resp = vendor_query.execute()
    vendors = vendor_resp.data or []

    # 3. Haversine pre-filter with generous buffer
    buffer_radius = radius_miles * 1.33
    results = []

    for vendor in vendors:
        v_lat = float(vendor["latitude"]) if vendor.get("latitude") else None
        v_lng = float(vendor["longitude"]) if vendor.get("longitude") else None

        if v_lat is None or v_lng is None:
            continue

        dist = haversine_distance(proj_lat, proj_lng, v_lat, v_lng)
        if dist is None:
            continue

        if dist <= buffer_radius:
            results.append({
                **vendor,
                "distance_miles": round(dist, 1),
            })

    # 4. Final filter at actual radius and sort
    results = [r for r in results if r["distance_miles"] <= radius_miles]
    results.sort(key=lambda r: r["distance_miles"])

    return results
