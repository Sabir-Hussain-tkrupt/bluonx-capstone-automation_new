"""
Integration tests — geocoding triggers on vendor/project create & update.

Uses FastAPI dependency overrides to mock BOTH auth and the Supabase client,
so no real Supabase instance is touched and no rows are created (the previous
version wrote to a live DB and 409'd on rerun). The geocoding service itself
is patched per-test to assert it is / isn't invoked and that its result flows
into the persisted row.
"""

import pytest
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.services.geocoding import GeocodingError
from tests._fakes import FakeResponse, FakeSupabase


# resolve_coordinates() lives in the service and is what the routers call, so
# the seam moved here from the old per-router `geocode_address` import. These
# tests therefore now cover the real coordinate-resolution rules (null on
# not-locatable, keep on lookup failure) rather than just the router glue.
_GEOCODE_TARGET = "app.services.geocoding.geocode_address"


@pytest.fixture(autouse=True)
def _api_key_configured():
    """resolve_coordinates() short-circuits with no key, which would make
    every assertion below vacuous."""
    with patch("app.services.geocoding.settings.GOOGLE_MAPS_API_KEY", "test-key"):
        yield


# ── Constants ─────────────────────────────────────────────────────────────

MOCK_LAT = Decimal("30.2672")
MOCK_LNG = Decimal("-97.7431")
_NOW = "2026-01-01T00:00:00+00:00"

FAKE_USER = {
    "user_id": str(uuid4()),
    "email": "pm@bluonx.dev",
    "full_name": "Test PM",
    "role": "project_manager",
    "is_active": True,
}


# ── Row builders (schema-accurate response rows) ──────────────────────────


def _vendor_row(**overrides) -> dict:
    base = {
        "id": str(uuid4()),
        "company_name": "Row Vendor",
        "address": None, "city": None, "state": None, "zip_code": None,
        "latitude": None, "longitude": None,
        "insurance_expiration_date": None,
        "insurance_coverage_amount": None,
        "bonding_capacity": None,
        "max_active_jobs": None,
        "current_active_jobs": 0,
        "onboarding_status": "pending",
        "status": "active",
        "notes": None,
        "created_at": _NOW, "updated_at": _NOW, "deleted_at": None,
    }
    base.update(overrides)
    return base


def _contact_row(**overrides) -> dict:
    base = {
        "id": str(uuid4()),
        "vendor_id": str(uuid4()),
        "full_name": "Contact",
        "email": "contact@test.com",
        "phone": None, "title": None,
        "is_primary": True,
        "created_at": _NOW, "updated_at": _NOW,
    }
    base.update(overrides)
    return base


def _project_row(**overrides) -> dict:
    base = {
        "id": str(uuid4()),
        "name": "Row Project",
        "description": None, "address": None, "city": None, "state": None,
        "zip_code": None, "latitude": None, "longitude": None, "budget": None,
        "status": "planning", "start_date": None, "estimated_end_date": None,
        "created_by": str(uuid4()),
        "created_at": _NOW, "updated_at": _NOW,
        "deleted_at": None, "archived_at": None, "archived_by": None,
    }
    base.update(overrides)
    return base


# ── Resolver + client fixtures ─────────────────────────────────────────────


def _resolver(mapping):
    """Build a FakeSupabase resolver from a {(table, op): value} mapping.

    A value may be a FakeResponse or a callable taking the write payload and
    returning one. Unmapped (table, op) pairs resolve to an empty result —
    which is exactly what the duplicate-name pre-check wants on create.
    """
    def _resolve(table, op, payload):
        value = mapping.get((table, op))
        if callable(value):
            return value(payload)
        if value is not None:
            return value
        return FakeResponse([])
    return _resolve


@pytest.fixture()
def make_client():
    """Factory: make_client(mapping) → TestClient wired to a FakeSupabase."""
    def _make(mapping):
        app.dependency_overrides[get_current_active_user] = lambda: FAKE_USER
        app.dependency_overrides[get_supabase] = lambda: FakeSupabase(_resolver(mapping))
        return TestClient(app)
    yield _make
    app.dependency_overrides.clear()


# ── Vendor Geocoding ────────────────────────────────────────────────────────


class TestVendorGeocodingIntegration:
    """Tests that vendor create/update triggers geocoding."""

    def test_create_vendor_triggers_geocode(self, make_client):
        """POST /api/v1/vendors with address should populate lat/lng."""
        client = make_client({
            ("vendors", "insert"): lambda p: FakeResponse([_vendor_row(**p)]),
            ("vendor_contacts", "insert"): lambda p: FakeResponse([_contact_row(**p)]),
        })
        with patch(
            _GEOCODE_TARGET,
            new_callable=AsyncMock,
            return_value=(MOCK_LAT, MOCK_LNG),
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
            )

        assert resp.status_code == 201
        data = resp.json()
        mock_geo.assert_awaited_once()
        # Lat/lng from geocoding should have been written into the row.
        assert data.get("latitude") is not None
        assert data.get("longitude") is not None

    def test_update_vendor_address_triggers_geocode(self, make_client):
        """PATCH vendor with address change should re-geocode."""
        vendor_id = uuid4()
        client = make_client({
            ("vendors", "select"): FakeResponse(_vendor_row(id=str(vendor_id))),
            ("vendors", "update"): lambda p: FakeResponse([_vendor_row(id=str(vendor_id), **p)]),
        })
        with patch(
            _GEOCODE_TARGET,
            new_callable=AsyncMock,
            return_value=(MOCK_LAT, MOCK_LNG),
        ) as mock_geo:
            resp = client.patch(
                f"/api/v1/vendors/{vendor_id}",
                json={"address": "456 New Ave", "city": "Dallas"},
            )

        assert resp.status_code == 200
        mock_geo.assert_awaited_once()

    def test_update_vendor_name_only_no_geocode(self, make_client):
        """PATCH with only company_name should NOT trigger geocoding."""
        vendor_id = uuid4()
        client = make_client({
            ("vendors", "select"): FakeResponse(_vendor_row(id=str(vendor_id))),
            ("vendors", "update"): lambda p: FakeResponse([_vendor_row(id=str(vendor_id), **p)]),
        })
        with patch(
            _GEOCODE_TARGET,
            new_callable=AsyncMock,
            return_value=(MOCK_LAT, MOCK_LNG),
        ) as mock_geo:
            resp = client.patch(
                f"/api/v1/vendors/{vendor_id}",
                json={"company_name": "Renamed Vendor"},
            )

        assert resp.status_code == 200
        mock_geo.assert_not_awaited()

    def test_create_vendor_geocode_failure_still_creates(self, make_client):
        """Geocoding failure should NOT block vendor creation."""
        client = make_client({
            ("vendors", "insert"): lambda p: FakeResponse([_vendor_row(**p)]),
            ("vendor_contacts", "insert"): lambda p: FakeResponse([_contact_row(**p)]),
        })
        with patch(
            _GEOCODE_TARGET,
            new_callable=AsyncMock,
            side_effect=GeocodingError("Geocoding service unavailable"),
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
            )

        # Vendor should still be created even though geocoding failed.
        assert resp.status_code == 201
        data = resp.json()
        # Lat/lng should be null since geocoding failed.
        assert data.get("latitude") is None
        assert data.get("longitude") is None

    def test_create_vendor_no_address_no_geocode(self, make_client):
        """Vendor without address fields should NOT trigger geocoding at all."""
        client = make_client({
            ("vendors", "insert"): lambda p: FakeResponse([_vendor_row(**p)]),
            ("vendor_contacts", "insert"): lambda p: FakeResponse([_contact_row(**p)]),
        })
        with patch(
            _GEOCODE_TARGET,
            new_callable=AsyncMock,
            return_value=(MOCK_LAT, MOCK_LNG),
        ) as mock_geo:
            resp = client.post(
                "/api/v1/vendors",
                json={
                    "company_name": "No Address Vendor",
                    "contacts": [
                        {"full_name": "Eve", "email": "eve@test.com", "is_primary": True}
                    ],
                },
            )

        assert resp.status_code == 201
        # Geocoding should not be called when there's no address.
        mock_geo.assert_not_awaited()


# ── Project Geocoding ───────────────────────────────────────────────────────


class TestProjectGeocodingIntegration:
    """Tests that project create/update triggers geocoding."""

    def test_create_project_triggers_geocode(self, make_client):
        """POST /api/v1/projects with address should populate lat/lng."""
        client = make_client({
            ("projects", "insert"): lambda p: FakeResponse([_project_row(**p)]),
        })
        with patch(
            _GEOCODE_TARGET,
            new_callable=AsyncMock,
            return_value=(MOCK_LAT, MOCK_LNG),
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
            )

        assert resp.status_code == 201
        data = resp.json()
        mock_geo.assert_awaited_once()
        assert data.get("latitude") is not None
        assert data.get("longitude") is not None

    def test_update_project_address_triggers_geocode(self, make_client):
        """PATCH project with address change should re-geocode."""
        project_id = uuid4()
        client = make_client({
            ("projects", "select"): FakeResponse(_project_row(id=str(project_id))),
            ("projects", "update"): lambda p: FakeResponse([_project_row(id=str(project_id), **p)]),
        })
        with patch(
            _GEOCODE_TARGET,
            new_callable=AsyncMock,
            return_value=(MOCK_LAT, MOCK_LNG),
        ) as mock_geo:
            resp = client.patch(
                f"/api/v1/projects/{project_id}",
                json={"address": "456 New Ave", "city": "Dallas"},
            )

        assert resp.status_code == 200
        mock_geo.assert_awaited_once()
