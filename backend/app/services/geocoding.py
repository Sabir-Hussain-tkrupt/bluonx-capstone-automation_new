"""
Google Geocoding API service.

Converts addresses to (latitude, longitude) coordinates.
Caches results with async LRU to avoid duplicate API calls.
Degrades gracefully when API key is missing or API fails.
"""

import logging
from decimal import Decimal

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GEOCODING_TIMEOUT = 5.0  # seconds


# ── Exceptions ──────────────────────────────────────────────────────────────


class GeocodingError(Exception):
    """Base exception for geocoding failures."""


class GeocodingRateLimitError(GeocodingError):
    """Raised when Google API returns OVER_QUERY_LIMIT or OVER_DAILY_LIMIT."""


class GeocodingAuthError(GeocodingError):
    """Raised when Google API returns REQUEST_DENIED (invalid/missing key)."""


# ── Address Normalization ───────────────────────────────────────────────────


def normalize_address(
    address: str | None,
    city: str | None,
    state: str | None,
    zip_code: str | None,
) -> str:
    """Normalize address parts into a single lowercase, trimmed string.

    Used as cache key so that "123 Main St" and "123 main st" share a
    cache entry. Returns empty string if all parts are empty/None.
    """
    parts = []
    for part in (address, city, state, zip_code):
        if part and part.strip():
            parts.append(part.strip().lower())
    return ", ".join(parts)


# ── Geocoding ───────────────────────────────────────────────────────────────

# Simple dict cache — avoids async_lru event-loop issues with uvicorn
_geocode_cache: dict[str, tuple[Decimal | None, Decimal | None]] = {}


async def _geocode_cached(normalized_address: str) -> tuple[Decimal | None, Decimal | None]:
    """Internal cached geocoding call. Keyed on normalized address string."""

    # Check cache first
    if normalized_address in _geocode_cache:
        logger.debug("Geocode cache HIT: %s", normalized_address)
        return _geocode_cache[normalized_address]

    logger.debug("Geocode cache MISS: %s — calling Google API", normalized_address)

    async with httpx.AsyncClient(timeout=GEOCODING_TIMEOUT) as client:
        response = await client.get(
            GEOCODING_URL,
            params={
                "address": normalized_address,
                "key": settings.GOOGLE_MAPS_API_KEY,
            },
        )
        response.raise_for_status()

    data = response.json()
    api_status = data.get("status", "UNKNOWN_ERROR")

    if api_status == "OK":
        results = data.get("results", [])
        if not results:
            _geocode_cache[normalized_address] = (None, None)
            return (None, None)
        location = results[0]["geometry"]["location"]
        lat = Decimal(str(location["lat"]))
        lng = Decimal(str(location["lng"]))
        logger.info("Geocoded '%s' → (%s, %s)", normalized_address, lat, lng)
        _geocode_cache[normalized_address] = (lat, lng)
        return (lat, lng)

    if api_status == "ZERO_RESULTS":
        logger.info("Geocode ZERO_RESULTS for '%s'", normalized_address)
        _geocode_cache[normalized_address] = (None, None)
        return (None, None)

    if api_status in ("OVER_QUERY_LIMIT", "OVER_DAILY_LIMIT"):
        error_msg = data.get("error_message", "Rate limit exceeded")
        raise GeocodingRateLimitError(error_msg)

    if api_status == "REQUEST_DENIED":
        error_msg = data.get("error_message", "Request denied — check API key")
        raise GeocodingAuthError(error_msg)

    # INVALID_REQUEST, UNKNOWN_ERROR, or anything else
    error_msg = data.get("error_message", f"Geocoding failed with status: {api_status}")
    raise GeocodingError(error_msg)


async def geocode_address(
    address: str | None,
    city: str | None,
    state: str | None,
    zip_code: str | None,
) -> tuple[Decimal | None, Decimal | None]:
    """Geocode an address to (latitude, longitude).

    Returns (None, None) when:
    - No API key is configured
    - All address fields are empty
    - Google returns ZERO_RESULTS (e.g. gibberish input)

    Raises:
    - GeocodingRateLimitError: OVER_QUERY_LIMIT / OVER_DAILY_LIMIT
    - GeocodingAuthError: REQUEST_DENIED (invalid key)
    - GeocodingError: network timeout, UNKNOWN_ERROR, etc.
    """
    # Guard: no API key → silent no-op
    if not settings.GOOGLE_MAPS_API_KEY:
        return (None, None)

    # Guard: no address data → nothing to geocode
    normalized = normalize_address(address, city, state, zip_code)
    if not normalized:
        return (None, None)

    try:
        lat, lng = await _geocode_cached(normalized)
        logger.info("geocode_address result for '%s': (%s, %s)", normalized, lat, lng)
        return (lat, lng)
    except httpx.TimeoutException as exc:
        raise GeocodingError(f"Geocoding request timed out: {exc}") from exc
    except httpx.HTTPError as exc:
        raise GeocodingError(f"Geocoding HTTP error: {exc}") from exc


def clear_geocode_cache() -> None:
    """Clear the geocoding cache. Useful for testing."""
    _geocode_cache.clear()
