"""
Tests for GET /api/v1/projects/{id}/nearby-vendors endpoint.

Fully mocked: the endpoint delegates to filter_vendors_by_distance (patched
here) and never touches the DB directly, so we override get_supabase with a
harmless fake and get_current_active_user with a static user. No real Supabase
instance, no rows created — consistent with the project-wide mock pattern.
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from tests._fakes import FakeResponse, FakeSupabase


FAKE_USER = {
    "user_id": str(uuid4()),
    "email": "pm@bluonx.dev",
    "full_name": "Test PM",
    "role": "project_manager",
    "is_active": True,
}

# Schema-accurate rows matching NearbyVendorResponse (UUID id + status field).
MOCK_NEARBY_RESULTS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "company_name": "Nearby Vendor",
        "city": "Austin",
        "state": "TX",
        "status": "active",
        "distance_miles": 5.2,
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "company_name": "Another Vendor",
        "city": "Round Rock",
        "state": "TX",
        "status": "active",
        "distance_miles": 18.7,
    },
]


@pytest.fixture()
def client():
    """TestClient with auth + Supabase dependencies overridden.

    The Supabase fake is never actually queried by this endpoint (the distance
    service is mocked), but get_supabase must resolve to *something*.
    """
    app.dependency_overrides[get_current_active_user] = lambda: FAKE_USER
    app.dependency_overrides[get_supabase] = lambda: FakeSupabase(
        lambda table, op, payload: FakeResponse([])
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestNearbyVendorsEndpoint:
    """Tests for the nearby-vendors API endpoint."""

    def test_get_nearby_vendors(self, client):
        """Returns vendors with distance_miles when project has coords."""
        project_id = uuid4()
        with patch(
            "app.routers.geocoding.filter_vendors_by_distance",
            new_callable=AsyncMock,
            return_value=MOCK_NEARBY_RESULTS,
        ):
            resp = client.get(f"/api/v1/projects/{project_id}/nearby-vendors")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["distance_miles"] == 5.2

    def test_get_nearby_vendors_with_trade_filter(self, client):
        """Query param trade_id is passed to the filtering service."""
        project_id = uuid4()
        with patch(
            "app.routers.geocoding.filter_vendors_by_distance",
            new_callable=AsyncMock,
            return_value=[MOCK_NEARBY_RESULTS[0]],
        ) as mock_filter:
            resp = client.get(
                f"/api/v1/projects/{project_id}/nearby-vendors?trade_id=some-trade-uuid"
            )

        assert resp.status_code == 200
        # Verify trade_id was forwarded to the service.
        assert mock_filter.await_args.kwargs["trade_id"] == "some-trade-uuid"

    def test_get_nearby_vendors_custom_radius(self, client):
        """Query param radius=50 is respected."""
        project_id = uuid4()
        with patch(
            "app.routers.geocoding.filter_vendors_by_distance",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_filter:
            resp = client.get(
                f"/api/v1/projects/{project_id}/nearby-vendors?radius=50"
            )

        assert resp.status_code == 200
        # Verify radius was forwarded to the service.
        assert mock_filter.await_args.kwargs["radius_miles"] == 50

    def test_get_nearby_vendors_project_no_coords(self, client):
        """Project without lat/lng → 400 error."""
        project_id = uuid4()
        with patch(
            "app.routers.geocoding.filter_vendors_by_distance",
            new_callable=AsyncMock,
            side_effect=ValueError("Project has no coordinates"),
        ):
            resp = client.get(f"/api/v1/projects/{project_id}/nearby-vendors")

        assert resp.status_code == 400

    def test_get_nearby_vendors_project_not_found(self, client):
        """Non-existent project → 404 error."""
        with patch(
            "app.routers.geocoding.filter_vendors_by_distance",
            new_callable=AsyncMock,
            side_effect=ValueError("Project not found"),
        ):
            resp = client.get(
                "/api/v1/projects/00000000-0000-0000-0000-000000000000/nearby-vendors"
            )

        assert resp.status_code == 404
