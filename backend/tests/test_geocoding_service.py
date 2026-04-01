"""
Tests for the geocoding service — backend/app/services/geocoding.py

All tests mock httpx calls. Zero real API calls to Google.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

import httpx


# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_geocode_response(status: str, results: list | None = None):
    """Build a mock Google Geocoding API JSON response."""
    body = {"status": status}
    if results is not None:
        body["results"] = results
    else:
        body["results"] = []
    return body


def _ok_result(lat: float = 30.2672, lng: float = -97.7431):
    """Single valid geocode result (Austin TX by default)."""
    return {
        "formatted_address": "123 Main St, Austin, TX 78701, USA",
        "geometry": {
            "location": {"lat": lat, "lng": lng},
            "location_type": "ROOFTOP",
        },
        "place_id": "ChIJLwPMoJm1RIYRetVp1EtGm10",
        "address_components": [
            {"long_name": "123", "short_name": "123", "types": ["street_number"]},
            {"long_name": "Main Street", "short_name": "Main St", "types": ["route"]},
            {"long_name": "Austin", "short_name": "Austin", "types": ["locality"]},
            {"long_name": "TX", "short_name": "TX", "types": ["administrative_area_level_1"]},
            {"long_name": "78701", "short_name": "78701", "types": ["postal_code"]},
        ],
    }


@pytest.fixture(autouse=True)
def _clear_geocode_cache():
    """Clear the geocode cache between tests so caching tests are deterministic."""
    yield
    try:
        from app.services.geocoding import clear_geocode_cache
        clear_geocode_cache()
    except (ImportError, AttributeError):
        pass


# ── Tests ───────────────────────────────────────────────────────────────────


class TestGeocodeAddress:
    """Unit tests for geocode_address()."""

    @pytest.mark.asyncio
    async def test_geocode_valid_address(self):
        """Valid address returns (lat, lng) tuple with Decimal values."""
        from app.services.geocoding import geocode_address

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_geocode_response(
            "OK", [_ok_result(30.2672, -97.7431)]
        )
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            lat, lng = await geocode_address("123 Main St", "Austin", "TX", "78701")

        assert lat is not None
        assert lng is not None
        assert isinstance(lat, Decimal)
        assert isinstance(lng, Decimal)
        # Austin TX approximate coords
        assert abs(float(lat) - 30.2672) < 0.01
        assert abs(float(lng) - (-97.7431)) < 0.01

    @pytest.mark.asyncio
    async def test_geocode_zero_results_returns_none(self):
        """Gibberish address like 'skrnd' returns (None, None) — no crash."""
        from app.services.geocoding import geocode_address

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_geocode_response("ZERO_RESULTS")
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            lat, lng = await geocode_address("skrnd", None, None, None)

        assert lat is None
        assert lng is None

    @pytest.mark.asyncio
    async def test_geocode_over_query_limit_raises(self):
        """OVER_QUERY_LIMIT status raises GeocodingRateLimitError."""
        from app.services.geocoding import geocode_address, GeocodingRateLimitError

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_geocode_response("OVER_QUERY_LIMIT")
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(GeocodingRateLimitError):
                await geocode_address("123 Main St", "Austin", "TX", "78701")

    @pytest.mark.asyncio
    async def test_geocode_request_denied_raises(self):
        """REQUEST_DENIED (invalid API key) raises GeocodingAuthError."""
        from app.services.geocoding import geocode_address, GeocodingAuthError

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_geocode_response(
            "REQUEST_DENIED"
        )
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(GeocodingAuthError):
                await geocode_address("123 Main St", "Austin", "TX", "78701")

    @pytest.mark.asyncio
    async def test_geocode_unknown_error_raises(self):
        """UNKNOWN_ERROR raises GeocodingError."""
        from app.services.geocoding import geocode_address, GeocodingError

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_geocode_response("UNKNOWN_ERROR")
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(GeocodingError):
                await geocode_address("123 Main St", "Austin", "TX", "78701")

    @pytest.mark.asyncio
    async def test_geocode_network_timeout_raises(self):
        """Network timeout raises GeocodingError."""
        from app.services.geocoding import geocode_address, GeocodingError

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.side_effect = httpx.TimeoutException("Connection timed out")
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(GeocodingError, match="timed out|timeout"):
                await geocode_address("123 Main St", "Austin", "TX", "78701")

    @pytest.mark.asyncio
    async def test_geocode_caching_avoids_duplicate_calls(self):
        """Two calls with same address should only hit the API once."""
        from app.services.geocoding import geocode_address

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_geocode_response(
            "OK", [_ok_result()]
        )
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            # First call — hits API
            lat1, lng1 = await geocode_address("123 Main St", "Austin", "TX", "78701")
            # Second call — should use cache
            lat2, lng2 = await geocode_address("123 Main St", "Austin", "TX", "78701")

        assert lat1 == lat2
        assert lng1 == lng2
        # httpx should only have been called once (cache hit on second call)
        assert instance.get.call_count == 1

    @pytest.mark.asyncio
    async def test_geocode_normalization_case_insensitive(self):
        """'123 Main St' and '123 main st' should hit the same cache entry."""
        from app.services.geocoding import geocode_address

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_geocode_response(
            "OK", [_ok_result()]
        )
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            await geocode_address("123 Main St", "Austin", "TX", "78701")
            await geocode_address("123 main st", "austin", "tx", "78701")

        # Should be a single API call — normalization made both keys identical
        assert instance.get.call_count == 1

    @pytest.mark.asyncio
    async def test_geocode_empty_address_returns_none(self):
        """All address fields None or empty → (None, None) without API call."""
        from app.services.geocoding import geocode_address

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            lat, lng = await geocode_address(None, None, None, None)

        assert lat is None
        assert lng is None
        # API should NOT have been called
        instance.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_geocode_empty_strings_returns_none(self):
        """All address fields empty strings → (None, None) without API call."""
        from app.services.geocoding import geocode_address

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            lat, lng = await geocode_address("", "", "", "")

        assert lat is None
        assert lng is None
        instance.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_geocode_partial_address_calls_api(self):
        """Only city + state provided → still calls API and returns result."""
        from app.services.geocoding import geocode_address

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_geocode_response(
            "OK", [_ok_result(30.2672, -97.7431)]
        )
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            lat, lng = await geocode_address(None, "Austin", "TX", None)

        assert lat is not None
        assert lng is not None
        instance.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_geocode_no_api_key_returns_none(self):
        """When GOOGLE_MAPS_API_KEY is None, return (None, None) without API call."""
        from app.services.geocoding import geocode_address

        with patch("app.services.geocoding.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with patch("app.services.geocoding.settings") as mock_settings:
                mock_settings.GOOGLE_MAPS_API_KEY = None

                lat, lng = await geocode_address("123 Main St", "Austin", "TX", "78701")

        assert lat is None
        assert lng is None
        instance.get.assert_not_called()


class TestNormalizeAddress:
    """Tests for the address normalization helper."""

    def test_normalize_strips_and_lowercases(self):
        from app.services.geocoding import normalize_address

        result = normalize_address("  123 Main St  ", " Austin ", " TX ", " 78701 ")
        assert result == "123 main st, austin, tx, 78701"

    def test_normalize_skips_none_fields(self):
        from app.services.geocoding import normalize_address

        result = normalize_address(None, "Austin", "TX", None)
        assert result == "austin, tx"

    def test_normalize_skips_empty_strings(self):
        from app.services.geocoding import normalize_address

        result = normalize_address("", "Austin", "", "78701")
        assert result == "austin, 78701"

    def test_normalize_all_empty_returns_empty(self):
        from app.services.geocoding import normalize_address

        result = normalize_address(None, None, None, None)
        assert result == ""

    def test_normalize_all_whitespace_returns_empty(self):
        from app.services.geocoding import normalize_address

        result = normalize_address("  ", "  ", "  ", "  ")
        assert result == ""
