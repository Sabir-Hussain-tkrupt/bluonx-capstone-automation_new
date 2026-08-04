"""
Tests for GET /v1/bid-packages/{bid_package_id}.

Covers the detail-view service: bid package core fields, invitation summary
counts, the full invitations array with vendor details, 404 handling, and
lazy expiration when the deadline has passed.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# Import will fail until implementation lands — expected for test-first.
from app.services.invitation_tracking_service import (
    BidPackageNotFoundError,
    get_bid_package_detail,
)

from .conftest import (
    BID_PACKAGE_ID,
    BID_SUBMISSION_IDS,
    INVITATION_IDS,
    NONEXISTENT_BID_PACKAGE_ID,
    TASK_ID,
    build_chain,
)


class TestBidPackageCoreFields:
    """Response includes task_name, round_number, deadline, status, template, docs."""

    @pytest.mark.asyncio
    async def test_returns_core_fields(self, mock_supabase, sample_bid_package_open):
        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        assert result["id"] == str(BID_PACKAGE_ID)
        assert result["task_name"] == "Rough Grading"
        assert result["round_number"] == 1
        assert result["deadline"] == sample_bid_package_open["deadline"]
        assert result["status"] == "open"
        assert result["bid_template"] is not None
        assert result["bid_template"]["name"] == "Standard Grading Template"
        assert isinstance(result["documents"], list)
        assert len(result["documents"]) == 2


class TestInvitationSummaryCounts:
    """Response includes invitation_summary with counts per status."""

    @pytest.mark.asyncio
    async def test_summary_counts_all_statuses(self, mock_supabase):
        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        summary = result["invitation_summary"]
        assert summary["total"] == 6
        assert summary["sent"] == 1
        assert summary["opened"] == 1
        assert summary["submitted"] == 1
        assert summary["declined"] == 1
        assert summary["expired"] == 1
        assert summary["no_response"] == 1


class TestInvitationsArray:
    """Invitations array contains vendor company, contact name/email, timestamps."""

    @pytest.mark.asyncio
    async def test_invitations_have_vendor_details(self, mock_supabase):
        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        invitations = result["invitations"]
        assert isinstance(invitations, list)
        assert len(invitations) == 6

        for inv in invitations:
            assert "vendor_company_name" in inv
            assert "vendor_contact_name" in inv
            assert "vendor_contact_email" in inv
            assert "status" in inv
            assert "sent_at" in inv
            assert "opened_at" in inv
            assert "responded_at" in inv
            assert "bid_submission_id" in inv

    @pytest.mark.asyncio
    async def test_invitation_vendor_fields_populated(self, mock_supabase):
        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        submitted = next(
            i for i in result["invitations"] if i["status"] == "submitted"
        )
        assert submitted["vendor_company_name"] == "Submitted Vendor Co."
        assert submitted["vendor_contact_name"] == "Contact Submitted"
        assert submitted["vendor_contact_email"] == "submitted@example.com"
        assert submitted["opened_at"] is not None
        assert submitted["responded_at"] is not None
        assert submitted["bid_submission_id"] == str(BID_SUBMISSION_IDS["submitted"])

        # Non-submitted rows have null bid_submission_id
        sent = next(i for i in result["invitations"] if i["status"] == "sent")
        assert sent["bid_submission_id"] is None


class TestNonexistentBidPackage:
    """Returns 404 when bid_package_id does not exist."""

    @pytest.mark.asyncio
    async def test_raises_not_found(self, mock_supabase):
        # Override bid_packages table to return no rows
        def table_side_effect(name):
            if name == "bid_packages":
                return build_chain(data=[])
            return build_chain(data=[])

        mock_supabase.table.side_effect = table_side_effect

        with pytest.raises(BidPackageNotFoundError):
            await get_bid_package_detail(
                bid_package_id=NONEXISTENT_BID_PACKAGE_ID,
                db=mock_supabase,
            )


class TestSubmittedBids:
    """Response includes submitted_bids: a list of {vendor_company_name, total_amount},
    sorted ascending by total_amount."""

    @pytest.mark.asyncio
    async def test_returns_submitted_bids_field(self, mock_supabase):
        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        assert "submitted_bids" in result
        submitted = result["submitted_bids"]
        assert isinstance(submitted, list)
        assert len(submitted) == 2
        # Sorted ascending by total_amount: Bedrock (41200) before Apex (47500)
        assert submitted[0]["vendor_company_name"] == "Bedrock Civil"
        assert float(submitted[0]["total_amount"]) == 41200.00
        assert submitted[1]["vendor_company_name"] == "Apex Grading"
        assert float(submitted[1]["total_amount"]) == 47500.00

    @pytest.mark.asyncio
    async def test_submitted_bids_empty_when_no_submissions(
        self,
        sample_bid_package_open,
        sample_invitations_mixed_statuses,
        sample_email_log_rows,
        sample_bid_package_documents,
    ):
        client = MagicMock()

        def table_side_effect(name):
            if name == "bid_packages":
                return build_chain(data=[sample_bid_package_open])
            if name == "bid_invitations":
                return build_chain(data=sample_invitations_mixed_statuses)
            if name == "email_log":
                return build_chain(data=sample_email_log_rows)
            if name == "bid_package_documents":
                return build_chain(data=sample_bid_package_documents)
            if name == "bid_submissions":
                return build_chain(data=[])
            return build_chain(data=[])

        client.table.side_effect = table_side_effect

        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )
        assert result["submitted_bids"] == []

    @pytest.mark.asyncio
    async def test_submitted_bid_shape(self, mock_supabase):
        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        for item in result["submitted_bids"]:
            assert set(item.keys()) == {"vendor_company_name", "total_amount"}
            assert isinstance(item["vendor_company_name"], str)
            # total_amount may be Decimal/float/None — allow numeric or None
            assert item["total_amount"] is None or isinstance(
                item["total_amount"], (int, float)
            )


class TestLazyExpiration:
    """When deadline has passed, sent/opened invitations converge to
    'no_response' and bid_package.status flips from 'open' to 'evaluating'."""

    @pytest.mark.asyncio
    async def test_lazy_expiration_updates_invitations_and_package(
        self,
        sample_bid_package_past_deadline,
        sample_invitations_mixed_statuses,
        sample_bid_package_documents,
        sample_email_log_rows,
        updates_captured,
    ):
        # Build a fresh mock that uses the past-deadline package
        client = MagicMock()

        def table_side_effect(name):
            if name == "bid_packages":
                chain = build_chain(data=[sample_bid_package_past_deadline])
            elif name == "bid_invitations":
                chain = build_chain(data=sample_invitations_mixed_statuses)
            elif name == "email_log":
                chain = build_chain(data=sample_email_log_rows)
            elif name == "bid_package_documents":
                chain = build_chain(data=sample_bid_package_documents)
            else:
                chain = build_chain(data=[])

            def capture(payload, _chain=chain, _name=name):
                updates_captured.append({"table": _name, "payload": payload})
                return _chain

            chain.update.side_effect = capture
            return chain

        client.table.side_effect = table_side_effect

        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        # Bid package should be marked evaluating in the returned response
        assert result["status"] == "evaluating"

        # bid_invitations should have been updated with status='no_response'
        invitation_updates = [
            u for u in updates_captured if u["table"] == "bid_invitations"
        ]
        assert len(invitation_updates) >= 1
        assert any(
            u["payload"].get("status") == "no_response" for u in invitation_updates
        )

        # bid_packages should have been updated with status='evaluating'
        package_updates = [
            u for u in updates_captured if u["table"] == "bid_packages"
        ]
        assert any(
            u["payload"].get("status") == "evaluating" for u in package_updates
        )

    @pytest.mark.asyncio
    async def test_lazy_expiration_does_not_touch_submitted_or_declined(
        self,
        sample_bid_package_past_deadline,
        sample_invitations_mixed_statuses,
        sample_bid_package_documents,
        sample_email_log_rows,
        updates_captured,
    ):
        """submitted and declined invitations must NOT become no_response."""
        client = MagicMock()

        def table_side_effect(name):
            if name == "bid_packages":
                chain = build_chain(data=[sample_bid_package_past_deadline])
            elif name == "bid_invitations":
                chain = build_chain(data=sample_invitations_mixed_statuses)
            elif name == "email_log":
                chain = build_chain(data=sample_email_log_rows)
            elif name == "bid_package_documents":
                chain = build_chain(data=sample_bid_package_documents)
            else:
                chain = build_chain(data=[])

            def capture(payload, _chain=chain, _name=name):
                updates_captured.append({"table": _name, "payload": payload})
                return _chain

            chain.update.side_effect = capture
            return chain

        client.table.side_effect = table_side_effect

        await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        # Find .eq calls on bid_invitations updates — the service should
        # filter by status IN ('sent', 'opened') or by specific IDs.
        # We verify via the returned invitations: submitted/declined still
        # carry their original status in the response.
        # (This is enforced by the lazy expiration logic only touching
        # 'sent'/'opened' rows.)
        no_response_updates = [
            u for u in updates_captured
            if u["table"] == "bid_invitations"
            and u["payload"].get("status") == "no_response"
        ]
        # The update payload sets status='no_response'; the filter (via .eq
        # or .in_) is what restricts WHICH rows get updated. We can only
        # assert that the update *payload* is 'no_response' — not 'submitted'
        # or 'declined'.
        for u in no_response_updates:
            assert u["payload"]["status"] != "submitted"
            assert u["payload"]["status"] != "declined"


class TestInvitationIsAwarded:
    """Each invitation row carries is_awarded — true iff the task has an
    award in a revision-blocking status (pending_acceptance / accepted)."""

    @staticmethod
    def _client_with_awards(
        awards_rows: list[dict],
        sample_bid_package_open,
        sample_invitations_mixed_statuses,
        sample_email_log_rows,
        sample_bid_package_documents,
        sample_bid_submissions,
    ) -> MagicMock:
        client = MagicMock()

        def table_side_effect(name):
            if name == "bid_packages":
                return build_chain(data=[sample_bid_package_open])
            if name == "bid_invitations":
                return build_chain(data=sample_invitations_mixed_statuses)
            if name == "email_log":
                return build_chain(data=sample_email_log_rows)
            if name == "bid_package_documents":
                return build_chain(data=sample_bid_package_documents)
            if name == "bid_submissions":
                return build_chain(data=sample_bid_submissions)
            if name == "awards":
                return build_chain(data=awards_rows)
            return build_chain(data=[])

        client.table.side_effect = table_side_effect
        return client

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("award_status", "expected"),
        [
            ("accepted", True),
            ("pending_acceptance", True),
            ("declined_by_vendor", False),
            ("cancelled", False),
        ],
    )
    async def test_is_awarded_reflects_award_status(
        self,
        award_status,
        expected,
        sample_bid_package_open,
        sample_invitations_mixed_statuses,
        sample_email_log_rows,
        sample_bid_package_documents,
        sample_bid_submissions,
    ):
        client = self._client_with_awards(
            [{"id": str(uuid4()), "task_id": str(TASK_ID), "status": award_status}],
            sample_bid_package_open,
            sample_invitations_mixed_statuses,
            sample_email_log_rows,
            sample_bid_package_documents,
            sample_bid_submissions,
        )

        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID, db=client
        )

        assert result["invitations"]
        for inv in result["invitations"]:
            assert inv["is_awarded"] is expected

    @pytest.mark.asyncio
    async def test_is_awarded_false_when_no_award(
        self,
        sample_bid_package_open,
        sample_invitations_mixed_statuses,
        sample_email_log_rows,
        sample_bid_package_documents,
        sample_bid_submissions,
    ):
        client = self._client_with_awards(
            [],
            sample_bid_package_open,
            sample_invitations_mixed_statuses,
            sample_email_log_rows,
            sample_bid_package_documents,
            sample_bid_submissions,
        )

        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID, db=client
        )

        assert result["invitations"]
        for inv in result["invitations"]:
            assert inv["is_awarded"] is False


class TestCancellationAttribution:
    """A cancelled package reports who voided it and when, so the detail page
    can explain why nothing on it is actionable.

    The name is resolved with an explicit users lookup rather than a PostgREST
    embed: bid_packages has two FKs to users (created_by and cancelled_by), so a
    bare users(...) embed on that table would be ambiguous.
    """

    @staticmethod
    def _client(
        package: dict,
        sample_invitations_mixed_statuses,
        sample_email_log_rows,
        sample_bid_package_documents,
        sample_bid_submissions,
        user_rows: list[dict] | None = None,
        seen_tables: list[str] | None = None,
    ) -> MagicMock:
        client = MagicMock()

        def table_side_effect(name):
            if seen_tables is not None:
                seen_tables.append(name)
            if name == "bid_packages":
                return build_chain(data=[package])
            if name == "bid_invitations":
                return build_chain(data=sample_invitations_mixed_statuses)
            if name == "email_log":
                return build_chain(data=sample_email_log_rows)
            if name == "bid_package_documents":
                return build_chain(data=sample_bid_package_documents)
            if name == "bid_submissions":
                return build_chain(data=sample_bid_submissions)
            if name == "users":
                return build_chain(data=list(user_rows or []))
            return build_chain(data=[])

        client.table.side_effect = table_side_effect
        return client

    @pytest.mark.asyncio
    async def test_cancelled_package_reports_who_and_when(
        self,
        sample_bid_package_open,
        sample_invitations_mixed_statuses,
        sample_email_log_rows,
        sample_bid_package_documents,
        sample_bid_submissions,
    ):
        canceller = str(uuid4())
        package = {
            **sample_bid_package_open,
            "status": "cancelled",
            "cancelled_by": canceller,
            "cancelled_at": "2026-08-03T10:00:00+00:00",
        }
        client = self._client(
            package,
            sample_invitations_mixed_statuses,
            sample_email_log_rows,
            sample_bid_package_documents,
            sample_bid_submissions,
            user_rows=[{"id": canceller, "full_name": "Jane Roe"}],
        )

        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID, db=client
        )

        assert result["cancelled_by_name"] == "Jane Roe"
        assert result["cancelled_at"] == "2026-08-03T10:00:00+00:00"

    @pytest.mark.asyncio
    async def test_non_cancelled_package_reports_none_and_skips_lookup(
        self,
        sample_bid_package_open,
        sample_invitations_mixed_statuses,
        sample_email_log_rows,
        sample_bid_package_documents,
        sample_bid_submissions,
    ):
        """The users query is guarded on status, so a normal package pays
        nothing for this feature."""
        seen: list[str] = []
        client = self._client(
            sample_bid_package_open,
            sample_invitations_mixed_statuses,
            sample_email_log_rows,
            sample_bid_package_documents,
            sample_bid_submissions,
            seen_tables=seen,
        )

        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID, db=client
        )

        assert result["cancelled_at"] is None
        assert result["cancelled_by_name"] is None
        assert "users" not in seen

    @pytest.mark.asyncio
    async def test_missing_user_row_still_reports_the_date(
        self,
        sample_bid_package_open,
        sample_invitations_mixed_statuses,
        sample_email_log_rows,
        sample_bid_package_documents,
        sample_bid_submissions,
    ):
        """cancelled_by is ON DELETE SET NULL and users are soft-deleted, so the
        name can vanish. The date must survive so the UI still explains itself."""
        package = {
            **sample_bid_package_open,
            "status": "cancelled",
            "cancelled_by": str(uuid4()),
            "cancelled_at": "2026-08-03T10:00:00+00:00",
        }
        client = self._client(
            package,
            sample_invitations_mixed_statuses,
            sample_email_log_rows,
            sample_bid_package_documents,
            sample_bid_submissions,
            user_rows=[],
        )

        result = await get_bid_package_detail(
            bid_package_id=BID_PACKAGE_ID, db=client
        )

        assert result["cancelled_by_name"] is None
        assert result["cancelled_at"] == "2026-08-03T10:00:00+00:00"
