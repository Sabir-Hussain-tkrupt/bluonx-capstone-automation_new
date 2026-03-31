"""
Tests for the distance calculation service — backend/app/services/distance.py

Tests Haversine formula and Routes API distance with mocked HTTP calls.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx


class TestHaversineDistance:
    """Unit tests for haversine_distance()."""

    def test_nyc_to_la(self):
        """NYC (40.7128, -74.0060) to LA (34.0522, -118.2437) ≈ 2,451 mi."""
        from app.services.distance import haversine_distance

        dist = haversine_distance(40.7128, -74.0060, 34.0522, -118.2437)
        assert dist is not None
        assert abs(dist - 2451) < 10  # within 10 miles

    def test_same_point_returns_zero(self):
        """Same coordinates → 0.0 miles."""
        from app.services.distance import haversine_distance

        dist = haversine_distance(30.2672, -97.7431, 30.2672, -97.7431)
        assert dist == 0.0

    def test_antipodal_points(self):
        """(0, 0) to (0, 180) ≈ 12,451 mi (half earth circumference)."""
        from app.services.distance import haversine_distance

        dist = haversine_distance(0, 0, 0, 180)
        assert dist is not None
        assert abs(dist - 12451) < 50  # within 50 miles

    def test_null_coords_returns_none(self):
        """Any None coordinate → None."""
        from app.services.distance import haversine_distance

        assert haversine_distance(None, -74.0, 34.0, -118.2) is None
        assert haversine_distance(40.7, None, 34.0, -118.2) is None
        assert haversine_distance(40.7, -74.0, None, -118.2) is None
        assert haversine_distance(40.7, -74.0, 34.0, None) is None

    def test_short_distance(self):
        """Two points ~1 mile apart — accurate within 0.1 mi.

        Using Austin TX: (30.2672, -97.7431) and a point ~1mi north.
        1 degree lat ≈ 69 miles, so ~0.0145 deg ≈ 1 mi.
        """
        from app.services.distance import haversine_distance

        lat1, lng1 = 30.2672, -97.7431
        lat2, lng2 = 30.2817, -97.7431  # ~1 mi north

        dist = haversine_distance(lat1, lng1, lat2, lng2)
        assert dist is not None
        assert abs(dist - 1.0) < 0.15

    def test_negative_latitudes(self):
        """Works correctly with Southern hemisphere coords."""
        from app.services.distance import haversine_distance

        # Sydney (-33.8688, 151.2093) to Melbourne (-37.8136, 144.9631) ≈ 443 mi (713 km)
        dist = haversine_distance(-33.8688, 151.2093, -37.8136, 144.9631)
        assert dist is not None
        assert abs(dist - 443) < 20


class TestRoutesApiDistance:
    """Tests for routes_api_distance() — mocked HTTP calls."""

    @pytest.mark.asyncio
    async def test_routes_api_returns_miles(self):
        """Mock Routes API response → correct conversion from meters to miles."""
        from app.services.distance import routes_api_distance

        # 100,000 meters = ~62.14 miles
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "originIndex": 0,
                "destinationIndex": 0,
                "distanceMeters": 100000,
                "duration": "3600s",
                "condition": "ROUTE_EXISTS",
            }
        ]
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.distance.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            dist = await routes_api_distance(30.27, -97.74, 29.42, -98.49)

        assert dist is not None
        assert abs(dist - 62.14) < 1.0

    @pytest.mark.asyncio
    async def test_routes_api_error_returns_none(self):
        """API failure (HTTP error) → returns None (caller should fallback)."""
        from app.services.distance import routes_api_distance

        with patch("app.services.distance.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.side_effect = httpx.HTTPStatusError(
                "500 Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            dist = await routes_api_distance(30.27, -97.74, 29.42, -98.49)

        assert dist is None

    @pytest.mark.asyncio
    async def test_routes_api_timeout_returns_none(self):
        """Network timeout → returns None."""
        from app.services.distance import routes_api_distance

        with patch("app.services.distance.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.side_effect = httpx.TimeoutException("Timed out")
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            dist = await routes_api_distance(30.27, -97.74, 29.42, -98.49)

        assert dist is None

    @pytest.mark.asyncio
    async def test_routes_api_no_key_returns_none(self):
        """No API key configured → returns None without calling API."""
        from app.services.distance import routes_api_distance

        with patch("app.services.distance.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with patch("app.services.distance.settings") as mock_settings:
                mock_settings.GOOGLE_MAPS_API_KEY = None
                dist = await routes_api_distance(30.27, -97.74, 29.42, -98.49)

        assert dist is None
        instance.post.assert_not_called()


class TestCalculateDistance:
    """Tests for calculate_distance() — Routes API with Haversine fallback."""

    @pytest.mark.asyncio
    async def test_uses_routes_api_when_available(self):
        """When Routes API succeeds, returns its result."""
        from app.services.distance import calculate_distance

        with patch("app.services.distance.routes_api_distance", new_callable=AsyncMock) as mock_routes:
            mock_routes.return_value = 62.14
            dist = await calculate_distance(30.27, -97.74, 29.42, -98.49)

        assert dist == 62.14
        mock_routes.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_haversine(self):
        """When Routes API returns None, falls back to Haversine."""
        from app.services.distance import calculate_distance

        with patch("app.services.distance.routes_api_distance", new_callable=AsyncMock) as mock_routes:
            mock_routes.return_value = None

            dist = await calculate_distance(40.7128, -74.0060, 34.0522, -118.2437)

        assert dist is not None
        assert abs(dist - 2451) < 10  # Haversine result

    @pytest.mark.asyncio
    async def test_null_coords_returns_none(self):
        """Any None coord → None without calling APIs."""
        from app.services.distance import calculate_distance

        dist = await calculate_distance(None, -97.74, 29.42, -98.49)
        assert dist is None
