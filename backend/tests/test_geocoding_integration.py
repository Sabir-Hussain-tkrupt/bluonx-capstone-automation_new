"""
Integration tests — geocoding triggers on vendor/project create & update.

Uses FastAPI TestClient with mocked geocoding service (no real Google calls).
Requires a real Supabase instance for DB operations.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch


# ── Helpers ─────────────────────────────────────────────────────────────────


MOCK_LAT = Decimal("30.2672")
MOCK_LNG = Decimal("-97.7431")


def _mock_geocode_success(*args, **kwargs):
    """Mocked geocode_address that always returns Austin TX coords."""
    return (MOCK_LAT, MOCK_LNG)


def _mock_geocode_failure(*args, **kwargs):
    """Mocked geocode_address that raises an error."""
    from app.services.geocoding import GeocodingError
    raise GeocodingError("Geocoding service unavailable")


def _mock_geocode_none(*args, **kwargs):
    """Mocked geocode_address that returns None (e.g., ZERO_RESULTS)."""
    return (None, None)


# ── Vendor Geocoding ────────────────────────────────────────────────────────


class TestVendorGeocodingIntegration:
    """Tests that vendor create/update triggers geocoding."""

    @pytest.mark.asyncio
    async def test_create_vendor_triggers_geocode(self, client, auth_headers):
        """POST /api/v1/vendors with address should populate lat/lng."""
        with patch(
            "app.routers.vendors.geocode_address",
            new_callable=AsyncMock,
            side_effect=_mock_geocode_success,
        ) as mock_geo:
            resp = client.post(
                "/api/v1/vendors",
                json={
                    "company_name": "Geo Test Vendor",
                    "address": "123 Main St",
                    "city": "Austin",
                    "state": "TX",
                    "zip_code": "78701",
                    "contacts": [
                        {"full_name": "John", "email": "john@test.com", "is_primary": True}
                    ],
                },
                headers=auth_headers,
            )

        assert resp.status_code == 201
        data = resp.json()
        mock_geo.assert_called_once()

        # Lat/lng should be populated from geocoding
        assert data.get("latitude") is not None
        assert data.get("longitude") is not None

    @pytest.mark.asyncio
    async def test_update_vendor_address_triggers_geocode(self, client, auth_headers):
        """PATCH vendor with address change should re-geocode."""
        # First create a vendor without geocoding
        with patch(
            "app.routers.vendors.geocode_address",
            new_callable=AsyncMock,
            side_effect=_mock_geocode_success,
        ):
            create_resp = client.post(
                "/api/v1/vendors",
                json={
                    "company_name": "Geo Update Vendor",
                    "address": "123 Old St",
                    "city": "Austin",
                    "state": "TX",
                    "contacts": [
                        {"full_name": "Jane", "email": "jane@test.com", "is_primary": True}
                    ],
                },
                headers=auth_headers,
            )
        vendor_id = create_resp.json()["id"]

        # Now update the address
        with patch(
            "app.routers.vendors.geocode_address",
            new_callable=AsyncMock,
            side_effect=_mock_geocode_success,
        ) as mock_geo:
            resp = client.patch(
                f"/api/v1/vendors/{vendor_id}",
                json={"address": "456 New Ave", "city": "Dallas"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        mock_geo.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_vendor_name_only_no_geocode(self, client, auth_headers):
        """PATCH with only company_name should NOT trigger geocoding."""
        with patch(
            "app.routers.vendors.geocode_address",
            new_callable=AsyncMock,
            side_effect=_mock_geocode_success,
        ):
            create_resp = client.post(
                "/api/v1/vendors",
                json={
                    "company_name": "No Geo Vendor",
                    "contacts": [
                        {"full_name": "Bob", "email": "bob@test.com", "is_primary": True}
                    ],
                },
                headers=auth_headers,
            )
        vendor_id = create_resp.json()["id"]

        with patch(
            "app.routers.vendors.geocode_address",
            new_callable=AsyncMock,
            side_effect=_mock_geocode_success,
        ) as mock_geo:
            resp = client.patch(
                f"/api/v1/vendors/{vendor_id}",
                json={"company_name": "Renamed Vendor"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        mock_geo.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_vendor_geocode_failure_still_creates(self, client, auth_headers):
        """Geocoding failure should NOT block vendor creation."""
        with patch(
            "app.routers.vendors.geocode_address",
            new_callable=AsyncMock,
            side_effect=_mock_geocode_failure,
        ):
            resp = client.post(
                "/api/v1/vendors",
                json={
                    "company_name": "Fail Geo Vendor",
                    "address": "Bad Address",
                    "city": "Nowhere",
                    "contacts": [
                        {"full_name": "Alice", "email": "alice@test.com", "is_primary": True}
                    ],
                },
                headers=auth_headers,
            )

        # Vendor should still be created even though geocoding failed
        assert resp.status_code == 201
        data = resp.json()
        # Lat/lng should be null since geocoding failed
        assert data.get("latitude") is None
        assert data.get("longitude") is None

    @pytest.mark.asyncio
    async def test_create_vendor_no_address_no_geocode(self, client, auth_headers):
        """Vendor without address fields should NOT trigger geocoding at all."""
        with patch(
            "app.routers.vendors.geocode_address",
            new_callable=AsyncMock,
            side_effect=_mock_geocode_success,
        ) as mock_geo:
            resp = client.post(
                "/api/v1/vendors",
                json={
                    "company_name": "No Address Vendor",
                    "contacts": [
                        {"full_name": "Eve", "email": "eve@test.com", "is_primary": True}
                    ],
                },
                headers=auth_headers,
            )

        assert resp.status_code == 201
        # Geocoding should not be called when there's no address
        mock_geo.assert_not_called()


# ── Project Geocoding ───────────────────────────────────────────────────────


class TestProjectGeocodingIntegration:
    """Tests that project create/update triggers geocoding."""

    @pytest.mark.asyncio
    async def test_create_project_triggers_geocode(self, client, auth_headers):
        """POST /api/v1/projects with address should populate lat/lng."""
        with patch(
            "app.routers.projects.geocode_address",
            new_callable=AsyncMock,
            side_effect=_mock_geocode_success,
        ) as mock_geo:
            resp = client.post(
                "/api/v1/projects",
                json={
                    "name": "Geo Test Project",
                    "address": "123 Main St",
                    "city": "Austin",
                    "state": "TX",
                    "zip_code": "78701",
                },
                headers=auth_headers,
            )

        assert resp.status_code == 201
        data = resp.json()
        mock_geo.assert_called_once()
        assert data.get("latitude") is not None
        assert data.get("longitude") is not None

    @pytest.mark.asyncio
    async def test_update_project_address_triggers_geocode(self, client, auth_headers):
        """PATCH project with address change should re-geocode."""
        with patch(
            "app.routers.projects.geocode_address",
            new_callable=AsyncMock,
            side_effect=_mock_geocode_success,
        ):
            create_resp = client.post(
                "/api/v1/projects",
                json={
                    "name": "Geo Update Project",
                    "address": "123 Old St",
                    "city": "Austin",
                    "state": "TX",
                },
                headers=auth_headers,
            )
        project_id = create_resp.json()["id"]

        with patch(
            "app.routers.projects.geocode_address",
            new_callable=AsyncMock,
            side_effect=_mock_geocode_success,
        ) as mock_geo:
            resp = client.patch(
                f"/api/v1/projects/{project_id}",
                json={"address": "456 New Ave", "city": "Dallas"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        mock_geo.assert_called_once()
