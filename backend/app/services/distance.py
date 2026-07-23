"""
Distance calculation primitives.

Provides:
- Haversine formula (pure math, no API calls)
- Google Routes API distance (driving distance)
- Combined distance with Haversine fallback

Proximity filtering itself lives in services/vendor_filtering.py, which is
the single path the app uses. A second implementation here
(filter_vendors_by_distance, feeding a nearby-vendors endpoint no page ever
called) computed straight-line distance only, so the two disagreed on what
"within 75 miles" meant. It was removed rather than reconciled.
"""

import logging
import math

import httpx

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
