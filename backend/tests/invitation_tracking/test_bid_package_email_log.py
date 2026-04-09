"""
Tests for GET /v1/bid-packages/{bid_package_id}/email-log.

Returns all email_log rows where reference_type='bid_invitations' and
reference_id matches an invitation in this bid package.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Import will fail until implementation lands — expected for test-first.
from app.services.invitation_tracking_service import (
    BidPackageNotFoundError,
    get_bid_package_email_log,
)

from .conftest import (
    BID_PACKAGE_ID,
    NONEXISTENT_BID_PACKAGE_ID,
    build_chain,
)


class TestReturnsRowsForInvitations:
    """Service returns every email_log row whose reference_id matches an
    invitation in the package."""

    @pytest.mark.asyncio
    async def test_returns_all_logged_emails(self, mock_supabase):
        result = await get_bid_package_email_log(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        assert isinstance(result, list)
        assert len(result) == 3


class TestRowShape:
    """Each row exposes the fields the PM UI needs."""

    @pytest.mark.asyncio
    async def test_row_has_expected_fields(self, mock_supabase):
        result = await get_bid_package_email_log(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        for row in result:
            assert "recipient_email" in row
            assert "email_type" in row
            assert "subject" in row
            assert "status" in row
            assert "sent_at" in row
            assert "error_message" in row

    @pytest.mark.asyncio
    async def test_failed_row_contains_error_message(self, mock_supabase):
        result = await get_bid_package_email_log(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        failed = [r for r in result if r["status"] == "failed"]
        assert len(failed) == 1
        assert failed[0]["error_message"] == "SMTP 550: mailbox not found"
        assert failed[0]["sent_at"] is None


class TestEmptyEmailLog:
    """When no emails have been logged, returns []."""

    @pytest.mark.asyncio
    async def test_empty_array(
        self,
        sample_bid_package_open,
        sample_invitations_mixed_statuses,
    ):
        client = MagicMock()

        def table_side_effect(name):
            if name == "bid_packages":
                return build_chain(data=[sample_bid_package_open])
            if name == "bid_invitations":
                return build_chain(data=sample_invitations_mixed_statuses)
            if name == "email_log":
                return build_chain(data=[])
            return build_chain(data=[])

        client.table.side_effect = table_side_effect

        result = await get_bid_package_email_log(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        assert result == []


class TestNonexistentBidPackage:
    """404 when bid_package_id doesn't exist."""

    @pytest.mark.asyncio
    async def test_raises_not_found(self):
        client = MagicMock()

        def table_side_effect(name):
            return build_chain(data=[])

        client.table.side_effect = table_side_effect

        with pytest.raises(BidPackageNotFoundError):
            await get_bid_package_email_log(
                bid_package_id=NONEXISTENT_BID_PACKAGE_ID,
                db=client,
            )
