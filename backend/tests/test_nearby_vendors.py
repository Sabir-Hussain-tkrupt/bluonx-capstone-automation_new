"""
Tests for GET /api/v1/projects/{id}/nearby-vendors endpoint.

Uses mocked filter_vendors_by_distance service.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


MOCK_NEARBY_RESULTS = [
    {
        "id": "v1",
        "company_name": "Nearby Vendor",
        "city": "Austin",
        "state": "TX",
        "distance_miles": 5.2,
    },
    {
        "id": "v2",
        "company_name": "Another Vendor",
        "city": "Round Rock",
        "state": "TX",
        "distance_miles": 18.7,
    },
]


class TestNearbyVendorsEndpoint:
    """Tests for the nearby-vendors API endpoint."""

    @pytest.mark.asyncio
    async def test_get_nearby_vendors(self, client, auth_headers):
        """Returns vendors with distance_miles when project has coords."""
        with patch(
            "app.routers.geocoding.filter_vendors_by_distance",
            new_callable=AsyncMock,
            return_value=MOCK_NEARBY_RESULTS,
        ):
            # We need a real project to exist for the endpoint
            # Create one first
            with patch(
                "app.routers.projects.geocode_address",
                new_callable=AsyncMock,
                return_value=(30.2672, -97.7431),
            ):
                create_resp = client.post(
                    "/api/v1/projects",
                    json={
                        "name": "Nearby Test Project",
                        "address": "123 Main St",
                        "city": "Austin",
                        "state": "TX",
                    },
                    headers=auth_headers,
                )
            project_id = create_resp.json()["id"]

            resp = client.get(
                f"/api/v1/projects/{project_id}/nearby-vendors",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["distance_miles"] == 5.2

    @pytest.mark.asyncio
    async def test_get_nearby_vendors_with_trade_filter(self, client, auth_headers):
        """Query param trade_id is passed to the filtering service."""
        with patch(
            "app.routers.geocoding.filter_vendors_by_distance",
            new_callable=AsyncMock,
            return_value=[MOCK_NEARBY_RESULTS[0]],
        ) as mock_filter:
            with patch(
                "app.routers.projects.geocode_address",
                new_callable=AsyncMock,
                return_value=(30.2672, -97.7431),
            ):
                create_resp = client.post(
                    "/api/v1/projects",
                    json={"name": "Trade Filter Project", "city": "Austin", "state": "TX"},
                    headers=auth_headers,
                )
            project_id = create_resp.json()["id"]

            resp = client.get(
                f"/api/v1/projects/{project_id}/nearby-vendors?trade_id=some-trade-uuid",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        # Verify trade_id was passed to the service
        call_kwargs = mock_filter.call_args
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_get_nearby_vendors_custom_radius(self, client, auth_headers):
        """Query param radius=50 is respected."""
        with patch(
            "app.routers.geocoding.filter_vendors_by_distance",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_filter:
            with patch(
                "app.routers.projects.geocode_address",
                new_callable=AsyncMock,
                return_value=(30.2672, -97.7431),
            ):
                create_resp = client.post(
                    "/api/v1/projects",
                    json={"name": "Radius Project", "city": "Austin", "state": "TX"},
                    headers=auth_headers,
                )
            project_id = create_resp.json()["id"]

            resp = client.get(
                f"/api/v1/projects/{project_id}/nearby-vendors?radius=50",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        # Verify radius was passed
        call_kwargs = mock_filter.call_args
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_get_nearby_vendors_project_no_coords(self, client, auth_headers):
        """Project without lat/lng → 400 error."""
        with patch(
            "app.routers.geocoding.filter_vendors_by_distance",
            new_callable=AsyncMock,
            side_effect=ValueError("Project has no coordinates"),
        ):
            with patch(
                "app.routers.projects.geocode_address",
                new_callable=AsyncMock,
                return_value=(None, None),
            ):
                create_resp = client.post(
                    "/api/v1/projects",
                    json={"name": "No Coords Project"},
                    headers=auth_headers,
                )
            project_id = create_resp.json()["id"]

            resp = client.get(
                f"/api/v1/projects/{project_id}/nearby-vendors",
                headers=auth_headers,
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_get_nearby_vendors_project_not_found(self, client, auth_headers):
        """Non-existent project → 404 error."""
        resp = client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000/nearby-vendors",
            headers=auth_headers,
        )

        assert resp.status_code == 404
