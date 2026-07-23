"""
resolve_coordinates(): the three outcomes an address lookup can have.

Collapsing these into one is what let stale coordinates survive an address
change. A vendor moved from Missouri to Texas kept its Missouri coordinates
whenever the new address failed to geocode, and then silently qualified or
disqualified for the wrong projects in the distance filter.
"""

import pytest
from unittest.mock import patch

from app.services.geocoding import (
    GeocodingAuthError,
    GeocodingError,
    GeocodingRateLimitError,
    address_fields_changed,
    resolve_coordinates,
)


TEXAS = ("500 W 2nd St", "Austin", "TX", "78701")


@pytest.mark.asyncio
async def test_success_returns_coordinates_and_no_warning():
    with patch("app.services.geocoding.settings.GOOGLE_MAPS_API_KEY", "k"), \
         patch("app.services.geocoding.geocode_address", return_value=("30.26", "-97.74")):
        updates, warning = await resolve_coordinates(*TEXAS)

    assert updates == {"latitude": "30.26", "longitude": "-97.74"}
    assert warning is None


@pytest.mark.asyncio
async def test_zero_results_nulls_the_stored_coordinates():
    """The core fix. Not locatable must clear the old position, not keep it."""
    with patch("app.services.geocoding.settings.GOOGLE_MAPS_API_KEY", "k"), \
         patch("app.services.geocoding.geocode_address", return_value=(None, None)):
        updates, warning = await resolve_coordinates("zzz nowhere", None, None, "00000")

    assert updates == {"latitude": None, "longitude": None}
    assert warning is not None
    assert "locate" in warning.lower()


@pytest.mark.asyncio
async def test_cleared_address_nulls_the_stored_coordinates():
    with patch("app.services.geocoding.settings.GOOGLE_MAPS_API_KEY", "k"), \
         patch("app.services.geocoding.geocode_address", return_value=(None, None)):
        updates, warning = await resolve_coordinates(None, None, None, None)

    assert updates == {"latitude": None, "longitude": None}
    assert warning is not None


@pytest.mark.parametrize(
    "exc",
    [
        GeocodingError("network down"),
        GeocodingRateLimitError("over quota"),
        GeocodingAuthError("bad key"),
    ],
)
@pytest.mark.asyncio
async def test_lookup_failure_leaves_stored_coordinates_alone(exc):
    """A Google outage must not strip coordinates off every record edited
    during it, so the patch is empty and the stored values stand."""
    with patch("app.services.geocoding.settings.GOOGLE_MAPS_API_KEY", "k"), \
         patch("app.services.geocoding.geocode_address", side_effect=exc):
        updates, warning = await resolve_coordinates(*TEXAS)

    assert updates == {}
    assert warning is not None
    assert "mapping service" in warning.lower()


@pytest.mark.asyncio
async def test_no_api_key_is_silent_and_touches_nothing():
    """Geocoding switched off is not a failure worth warning about on
    every save, and must not clear coordinates geocoded earlier."""
    with patch("app.services.geocoding.settings.GOOGLE_MAPS_API_KEY", None):
        updates, warning = await resolve_coordinates(*TEXAS)

    assert updates == {}
    assert warning is None


@pytest.mark.asyncio
async def test_failure_warning_differs_from_not_locatable_warning():
    """The two cases need different user-facing text: one means fix the
    address, the other means try again later."""
    with patch("app.services.geocoding.settings.GOOGLE_MAPS_API_KEY", "k"):
        with patch("app.services.geocoding.geocode_address", return_value=(None, None)):
            _, not_locatable = await resolve_coordinates(*TEXAS)
        with patch("app.services.geocoding.geocode_address", side_effect=GeocodingError("x")):
            _, failed = await resolve_coordinates(*TEXAS)

    assert not_locatable != failed


class TestAddressFieldsChanged:
    def test_detects_each_address_field(self):
        for field in ("address", "city", "state", "zip_code"):
            assert address_fields_changed({field: "x"}) is True

    def test_ignores_non_address_updates(self):
        assert address_fields_changed({"company_name": "New Name"}) is False
        assert address_fields_changed({}) is False

    def test_detects_an_explicit_null(self):
        """Clearing the address is an address change and must re-run."""
        assert address_fields_changed({"address": None}) is True
