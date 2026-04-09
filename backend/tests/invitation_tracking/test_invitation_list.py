"""
Tests for GET /v1/bid-packages/{bid_package_id}/invitations.

Covers listing all invitations with joined vendor details, filtering by
status, empty-result behavior, and 404 for nonexistent bid packages.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Import will fail until implementation lands — expected for test-first.
from app.services.invitation_tracking_service import (
    BidPackageNotFoundError,
    list_invitations,
)

from .conftest import (
    BID_PACKAGE_ID,
    NONEXISTENT_BID_PACKAGE_ID,
    build_chain,
)


class TestListAllInvitations:
    """Without a filter, returns every invitation for the bid package."""

    @pytest.mark.asyncio
    async def test_returns_all_six_invitations(self, mock_supabase):
        result = await list_invitations(
            bid_package_id=BID_PACKAGE_ID,
            status_filter=None,
            db=mock_supabase,
        )

        assert isinstance(result, list)
        assert len(result) == 6

    @pytest.mark.asyncio
    async def test_each_invitation_has_vendor_details(self, mock_supabase):
        result = await list_invitations(
            bid_package_id=BID_PACKAGE_ID,
            status_filter=None,
            db=mock_supabase,
        )

        for inv in result:
            assert "vendor_company_name" in inv
            assert "vendor_contact_name" in inv
            assert "vendor_contact_email" in inv
            assert "status" in inv
            assert "sent_at" in inv
            assert "opened_at" in inv
            assert "responded_at" in inv


class TestFilterByStatus:
    """?status=submitted returns only matching invitations."""

    @pytest.mark.asyncio
    async def test_filter_submitted_only(
        self,
        sample_bid_package_open,
        sample_invitations_mixed_statuses,
    ):
        # Build mock where bid_invitations returns ONLY the submitted row
        # — simulating the .eq("status", "submitted") filter at DB level.
        client = MagicMock()
        submitted_only = [
            i for i in sample_invitations_mixed_statuses if i["status"] == "submitted"
        ]

        def table_side_effect(name):
            if name == "bid_packages":
                return build_chain(data=[sample_bid_package_open])
            if name == "bid_invitations":
                return build_chain(data=submitted_only)
            return build_chain(data=[])

        client.table.side_effect = table_side_effect

        result = await list_invitations(
            bid_package_id=BID_PACKAGE_ID,
            status_filter="submitted",
            db=client,
        )

        assert len(result) == 1
        assert result[0]["status"] == "submitted"


class TestEmptyFilter:
    """Returns [] when filter matches no invitations."""

    @pytest.mark.asyncio
    async def test_empty_array_when_no_matches(
        self,
        sample_bid_package_open,
    ):
        client = MagicMock()

        def table_side_effect(name):
            if name == "bid_packages":
                return build_chain(data=[sample_bid_package_open])
            if name == "bid_invitations":
                return build_chain(data=[])
            return build_chain(data=[])

        client.table.side_effect = table_side_effect

        result = await list_invitations(
            bid_package_id=BID_PACKAGE_ID,
            status_filter="no_response",
            db=client,
        )

        assert result == []


class TestNonexistentBidPackage:
    """Returns 404 for a bid_package_id that doesn't exist."""

    @pytest.mark.asyncio
    async def test_raises_not_found(self):
        client = MagicMock()

        def table_side_effect(name):
            return build_chain(data=[])

        client.table.side_effect = table_side_effect

        with pytest.raises(BidPackageNotFoundError):
            await list_invitations(
                bid_package_id=NONEXISTENT_BID_PACKAGE_ID,
                status_filter=None,
                db=client,
            )
