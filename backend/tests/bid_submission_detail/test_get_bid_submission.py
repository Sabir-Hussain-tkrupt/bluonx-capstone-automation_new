"""
Tests for GET /api/v1/bid-submissions/{submission_id} (Task 6.2 — PM single
bid detail view).

Verifies the PM-facing detail shape, sort_order normalization, signed URLs
on attachments, 404/401 handling, and direct-assign visibility.
"""

from __future__ import annotations

import pytest

from app.services.bid_submission_detail_service import (
    BidSubmissionNotFoundError,
    get_pm_bid_submission_detail,
)

from .conftest import (
    LINE_ITEM_IDS,
    NONEXISTENT_SUBMISSION_ID,
    SIGNED_URL_TEMPLATE,
    SUBMISSION_ID,
)


URL = f"/api/v1/bid-submissions/{SUBMISSION_ID}"


class TestServiceShape:
    """The service returns the full PM detail shape."""

    @pytest.mark.asyncio
    async def test_returns_top_level_fields(self, mock_supabase):
        result = await get_pm_bid_submission_detail(
            submission_id=SUBMISSION_ID, db=mock_supabase
        )

        assert result["id"] == str(SUBMISSION_ID)
        assert result["bid_invitation_id"] is not None
        assert result["status"] == "submitted"
        assert result["is_direct_assign"] is False
        assert result["vendor_company_name"] == "Apex Grading"
        assert result["vendor_contact_name"] == "Jane Roe"
        assert result["vendor_contact_email"] == "jane@apex.example.com"
        assert result["vendor_notes"] == (
            "Includes mobilization and demobilization."
        )
        assert result["submitted_at"] is not None
        assert float(result["total_amount"]) == 47500.00

    @pytest.mark.asyncio
    async def test_line_items_sorted_by_sort_order(self, mock_supabase):
        result = await get_pm_bid_submission_detail(
            submission_id=SUBMISSION_ID, db=mock_supabase
        )

        line_items = result["line_items"]
        assert len(line_items) == 3
        # Conftest seeds them out of order — service must sort by sort_order ascending
        assert [li["sort_order"] for li in line_items] == [0, 1, 2]
        assert line_items[0]["id"] == str(LINE_ITEM_IDS[0])
        assert line_items[1]["id"] == str(LINE_ITEM_IDS[1])
        assert line_items[2]["id"] == str(LINE_ITEM_IDS[2])

    @pytest.mark.asyncio
    async def test_attachments_have_signed_urls(self, mock_supabase):
        result = await get_pm_bid_submission_detail(
            submission_id=SUBMISSION_ID, db=mock_supabase
        )

        attachments = result["attachments"]
        assert len(attachments) == 2
        for att in attachments:
            assert att["download_url"].startswith("https://signed.example.com/")
            assert att["download_url_expires_in"] == 3600
        assert attachments[0]["download_url"] == SIGNED_URL_TEMPLATE.format(
            path=f"{SUBMISSION_ID}/scope.pdf"
        )


class TestNotFound:
    @pytest.mark.asyncio
    async def test_raises_not_found(self, mock_supabase_not_found):
        with pytest.raises(BidSubmissionNotFoundError):
            await get_pm_bid_submission_detail(
                submission_id=NONEXISTENT_SUBMISSION_ID,
                db=mock_supabase_not_found,
            )


class TestEmptyExtras:
    """Empty notes / no line items / no attachments serialize cleanly."""

    @pytest.mark.asyncio
    async def test_empty_optional_sections(self, mock_supabase_empty_extras):
        result = await get_pm_bid_submission_detail(
            submission_id=SUBMISSION_ID, db=mock_supabase_empty_extras
        )

        assert result["vendor_notes"] is None
        assert result["line_items"] == []
        assert result["attachments"] == []


class TestDirectAssign:
    @pytest.mark.asyncio
    async def test_direct_assign_flag(self, mock_supabase_direct_assign):
        result = await get_pm_bid_submission_detail(
            submission_id=SUBMISSION_ID, db=mock_supabase_direct_assign
        )

        assert result["is_direct_assign"] is True
        assert result["status"] == "submitted"


# ── HTTP-layer tests via FastAPI TestClient ────────────────────────────────


class TestEndpoint200:
    def test_returns_200_with_full_shape(self, client_with_overrides):
        resp = client_with_overrides.get(URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(SUBMISSION_ID)
        assert body["vendor_company_name"] == "Apex Grading"
        assert isinstance(body["line_items"], list)
        assert isinstance(body["attachments"], list)
        assert body["attachments"][0]["download_url"].startswith("https://")
        assert body["is_direct_assign"] is False
        # Non-superseded original: revision metadata defaults.
        assert body["is_superseded"] is False
        assert body["supersedes_submission_id"] is None
        assert body["revision_number"] == 1


class TestEndpoint404:
    def test_unknown_submission_returns_404(self, client_not_found):
        resp = client_not_found.get(URL)
        assert resp.status_code == 404


class TestEndpoint401:
    def test_missing_auth_header_rejected(self, client_no_auth):
        resp = client_no_auth.get(URL)
        # FastAPI's HTTPBearer returns 403 when no Authorization header is
        # supplied; both 401 and 403 indicate an unauthenticated request was
        # not allowed through.
        assert resp.status_code in (401, 403)


class TestEndpointDirectAssign:
    def test_direct_assign_fetchable(self, client_direct_assign):
        resp = client_direct_assign.get(URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_direct_assign"] is True


class TestEndpointEmptyExtras:
    def test_empty_extras_serialize(self, client_empty_extras):
        resp = client_empty_extras.get(URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["vendor_notes"] is None
        assert body["line_items"] == []
        assert body["attachments"] == []
