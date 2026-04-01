"""
Tests for vendor distance filtering — filter_vendors_by_distance()

Uses mocked Supabase queries and mocked distance calculations.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── Test data ───────────────────────────────────────────────────────────────

# Project at Austin TX
PROJECT_LAT = 30.2672
PROJECT_LNG = -97.7431

# Vendors at various distances from Austin TX
VENDOR_NEARBY = {
    "id": "v1",
    "company_name": "Nearby Vendor",
    "latitude": "30.30",     # ~2 mi north
    "longitude": "-97.74",
    "status": "active",
}

VENDOR_WITHIN_75 = {
    "id": "v2",
    "company_name": "Within 75mi Vendor",
    "latitude": "29.42",     # San Antonio ~75 mi south
    "longitude": "-98.49",
    "status": "active",
}

VENDOR_OUTSIDE_75 = {
    "id": "v3",
    "company_name": "Far Away Vendor",
    "latitude": "32.78",     # Dallas ~195 mi north
    "longitude": "-96.80",
    "status": "active",
}

VENDOR_NO_COORDS = {
    "id": "v4",
    "company_name": "No Coords Vendor",
    "latitude": None,
    "longitude": None,
    "status": "active",
}

PROJECT_DATA = {
    "id": "p1",
    "latitude": str(PROJECT_LAT),
    "longitude": str(PROJECT_LNG),
}

PROJECT_NO_COORDS = {
    "id": "p2",
    "latitude": None,
    "longitude": None,
}


class TestFilterVendorsByDistance:
    """Tests for filter_vendors_by_distance()."""

    @pytest.mark.asyncio
    async def test_filter_vendors_within_radius(self):
        """Vendors within 75mi returned, those outside excluded."""
        from app.services.distance import filter_vendors_by_distance

        mock_db = MagicMock()

        # Mock project lookup
        project_query = MagicMock()
        project_query.select.return_value = project_query
        project_query.eq.return_value = project_query
        project_query.is_.return_value = project_query
        project_query.single.return_value = project_query
        project_query.execute.return_value = MagicMock(data=PROJECT_DATA)

        # Mock vendor lookup — returns all vendors
        vendor_query = MagicMock()
        vendor_query.select.return_value = vendor_query
        vendor_query.is_.return_value = vendor_query
        vendor_query.not_.is_.return_value = vendor_query
        vendor_query.execute.return_value = MagicMock(
            data=[VENDOR_NEARBY, VENDOR_WITHIN_75, VENDOR_OUTSIDE_75, VENDOR_NO_COORDS]
        )

        def table_side_effect(name):
            if name == "projects":
                return project_query
            return vendor_query

        mock_db.table.side_effect = table_side_effect

        results = await filter_vendors_by_distance(
            db=mock_db,
            project_id="p1",
            radius_miles=75,
        )

        # Should include nearby and within-75 vendors only
        result_ids = [r["id"] for r in results]
        assert "v1" in result_ids  # ~2 mi
        assert "v2" in result_ids  # ~75 mi (border — SA is about 75mi from Austin)
        assert "v3" not in result_ids  # ~195 mi
        assert "v4" not in result_ids  # no coords

    @pytest.mark.asyncio
    async def test_filter_all_outside_radius_returns_empty(self):
        """When all vendors are beyond radius, return empty list."""
        from app.services.distance import filter_vendors_by_distance

        mock_db = MagicMock()

        project_query = MagicMock()
        project_query.select.return_value = project_query
        project_query.eq.return_value = project_query
        project_query.is_.return_value = project_query
        project_query.single.return_value = project_query
        project_query.execute.return_value = MagicMock(data=PROJECT_DATA)

        vendor_query = MagicMock()
        vendor_query.select.return_value = vendor_query
        vendor_query.is_.return_value = vendor_query
        vendor_query.not_.is_.return_value = vendor_query
        vendor_query.execute.return_value = MagicMock(data=[VENDOR_OUTSIDE_75])

        def table_side_effect(name):
            if name == "projects":
                return project_query
            return vendor_query

        mock_db.table.side_effect = table_side_effect

        results = await filter_vendors_by_distance(
            db=mock_db,
            project_id="p1",
            radius_miles=75,
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_filter_vendor_without_coords_excluded(self):
        """Vendor with null lat/lng is excluded gracefully — no crash."""
        from app.services.distance import filter_vendors_by_distance

        mock_db = MagicMock()

        project_query = MagicMock()
        project_query.select.return_value = project_query
        project_query.eq.return_value = project_query
        project_query.is_.return_value = project_query
        project_query.single.return_value = project_query
        project_query.execute.return_value = MagicMock(data=PROJECT_DATA)

        vendor_query = MagicMock()
        vendor_query.select.return_value = vendor_query
        vendor_query.is_.return_value = vendor_query
        vendor_query.not_.is_.return_value = vendor_query
        vendor_query.execute.return_value = MagicMock(data=[VENDOR_NO_COORDS])

        def table_side_effect(name):
            if name == "projects":
                return project_query
            return vendor_query

        mock_db.table.side_effect = table_side_effect

        results = await filter_vendors_by_distance(
            db=mock_db,
            project_id="p1",
            radius_miles=75,
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_filter_empty_vendor_set(self):
        """No vendors in DB → empty list."""
        from app.services.distance import filter_vendors_by_distance

        mock_db = MagicMock()

        project_query = MagicMock()
        project_query.select.return_value = project_query
        project_query.eq.return_value = project_query
        project_query.is_.return_value = project_query
        project_query.single.return_value = project_query
        project_query.execute.return_value = MagicMock(data=PROJECT_DATA)

        vendor_query = MagicMock()
        vendor_query.select.return_value = vendor_query
        vendor_query.is_.return_value = vendor_query
        vendor_query.not_.is_.return_value = vendor_query
        vendor_query.execute.return_value = MagicMock(data=[])

        def table_side_effect(name):
            if name == "projects":
                return project_query
            return vendor_query

        mock_db.table.side_effect = table_side_effect

        results = await filter_vendors_by_distance(
            db=mock_db,
            project_id="p1",
            radius_miles=75,
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_filter_project_without_coords_raises(self):
        """Project has null lat/lng → raises ValueError."""
        from app.services.distance import filter_vendors_by_distance

        mock_db = MagicMock()

        project_query = MagicMock()
        project_query.select.return_value = project_query
        project_query.eq.return_value = project_query
        project_query.is_.return_value = project_query
        project_query.single.return_value = project_query
        project_query.execute.return_value = MagicMock(data=PROJECT_NO_COORDS)

        mock_db.table.return_value = project_query

        with pytest.raises(ValueError, match="coordinates"):
            await filter_vendors_by_distance(
                db=mock_db,
                project_id="p2",
                radius_miles=75,
            )

    @pytest.mark.asyncio
    async def test_filter_custom_radius(self):
        """Custom radius_miles=10 filters correctly (only very nearby)."""
        from app.services.distance import filter_vendors_by_distance

        mock_db = MagicMock()

        project_query = MagicMock()
        project_query.select.return_value = project_query
        project_query.eq.return_value = project_query
        project_query.is_.return_value = project_query
        project_query.single.return_value = project_query
        project_query.execute.return_value = MagicMock(data=PROJECT_DATA)

        vendor_query = MagicMock()
        vendor_query.select.return_value = vendor_query
        vendor_query.is_.return_value = vendor_query
        vendor_query.not_.is_.return_value = vendor_query
        vendor_query.execute.return_value = MagicMock(
            data=[VENDOR_NEARBY, VENDOR_WITHIN_75, VENDOR_OUTSIDE_75]
        )

        def table_side_effect(name):
            if name == "projects":
                return project_query
            return vendor_query

        mock_db.table.side_effect = table_side_effect

        results = await filter_vendors_by_distance(
            db=mock_db,
            project_id="p1",
            radius_miles=10,
        )

        result_ids = [r["id"] for r in results]
        assert "v1" in result_ids   # ~2 mi — within 10
        assert "v2" not in result_ids  # ~75 mi — outside 10
        assert "v3" not in result_ids  # ~195 mi — outside 10

    @pytest.mark.asyncio
    async def test_filter_with_trade_id(self):
        """When trade_id is provided, only vendors with that trade are considered."""
        from app.services.distance import filter_vendors_by_distance

        mock_db = MagicMock()

        project_query = MagicMock()
        project_query.select.return_value = project_query
        project_query.eq.return_value = project_query
        project_query.is_.return_value = project_query
        project_query.single.return_value = project_query
        project_query.execute.return_value = MagicMock(data=PROJECT_DATA)

        # Vendor trades query — only v1 has the target trade
        trade_query = MagicMock()
        trade_query.select.return_value = trade_query
        trade_query.eq.return_value = trade_query
        trade_query.execute.return_value = MagicMock(
            data=[{"vendor_id": "v1"}]
        )

        # Vendor query — returns all, but should be filtered by trade
        vendor_query = MagicMock()
        vendor_query.select.return_value = vendor_query
        vendor_query.is_.return_value = vendor_query
        vendor_query.not_.is_.return_value = vendor_query
        vendor_query.in_.return_value = vendor_query
        vendor_query.execute.return_value = MagicMock(data=[VENDOR_NEARBY])

        call_count = {"n": 0}

        def table_side_effect(name):
            if name == "projects":
                return project_query
            if name == "vendor_trades":
                return trade_query
            return vendor_query

        mock_db.table.side_effect = table_side_effect

        results = await filter_vendors_by_distance(
            db=mock_db,
            project_id="p1",
            trade_id="t1",
            radius_miles=75,
        )

        result_ids = [r["id"] for r in results]
        assert "v1" in result_ids

    @pytest.mark.asyncio
    async def test_results_include_distance_miles(self):
        """Each result should include a distance_miles field."""
        from app.services.distance import filter_vendors_by_distance

        mock_db = MagicMock()

        project_query = MagicMock()
        project_query.select.return_value = project_query
        project_query.eq.return_value = project_query
        project_query.is_.return_value = project_query
        project_query.single.return_value = project_query
        project_query.execute.return_value = MagicMock(data=PROJECT_DATA)

        vendor_query = MagicMock()
        vendor_query.select.return_value = vendor_query
        vendor_query.is_.return_value = vendor_query
        vendor_query.not_.is_.return_value = vendor_query
        vendor_query.execute.return_value = MagicMock(data=[VENDOR_NEARBY])

        def table_side_effect(name):
            if name == "projects":
                return project_query
            return vendor_query

        mock_db.table.side_effect = table_side_effect

        results = await filter_vendors_by_distance(
            db=mock_db,
            project_id="p1",
            radius_miles=75,
        )

        assert len(results) == 1
        assert "distance_miles" in results[0]
        assert isinstance(results[0]["distance_miles"], float)
        assert results[0]["distance_miles"] > 0
