"""
Happy-path tests for bid package creation with invitation sending.

Creation is atomic: a single fn_create_bid_package_with_invitations RPC writes
the bid_packages row, bid_package_documents, bid_invitations (as 'pending_send'),
magic_link_tokens, and flips a draft task to 'bidding'. Emails are sent afterward
and each invitation is reconciled to 'sent' / 'send_failed'. These tests assert
the RPC contract plus the email phase.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from .conftest import (
    BID_TEMPLATE_ID,
    DOC_IDS,
    PM_USER_ID,
    TASK_ID,
    VENDOR_IDS,
    configure_create_rpc,
)

from app.services.bid_package_service import create_bid_package_with_invitations


def _create_rpc_params(mock_supabase) -> dict:
    """Return the single fn_create_bid_package_with_invitations call's params."""
    calls = [
        c
        for c in mock_supabase.rpc.call_args_list
        if c.args and c.args[0] == "fn_create_bid_package_with_invitations"
    ]
    assert len(calls) == 1, "creation RPC should be called exactly once"
    return calls[0].args[1]


class TestBidPackageHappyPath:
    """Full happy-path: 1 template, 2 documents, 3 vendors."""

    @pytest.mark.asyncio
    async def test_creates_bid_package_via_atomic_rpc(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
        future_deadline,
    ):
        """The package is created through the atomic RPC with the core fields."""
        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        params = _create_rpc_params(mock_supabase)
        assert params["p_task_id"] == str(TASK_ID)
        assert params["p_bid_template_id"] == str(BID_TEMPLATE_ID)
        assert params["p_created_by"] == str(PM_USER_ID)
        assert params["p_deadline"] == future_deadline.isoformat()
        assert result is not None

    @pytest.mark.asyncio
    async def test_passes_documents_to_rpc(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """Selected project documents are passed to the RPC for atomic insert."""
        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        params = _create_rpc_params(mock_supabase)
        assert params["p_project_document_ids"] == [str(d) for d in DOC_IDS]

    @pytest.mark.asyncio
    async def test_passes_one_vendor_entry_per_selection(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """One p_vendors entry per vendor_selection, with the right vendor ids."""
        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        params = _create_rpc_params(mock_supabase)
        vendors = params["p_vendors"]
        assert len(vendors) == 3
        assert {v["vendor_id"] for v in vendors} == {str(v) for v in VENDOR_IDS}

    @pytest.mark.asyncio
    async def test_each_vendor_gets_a_unique_token_hash(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """Each vendor entry carries a distinct, non-empty token hash."""
        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        params = _create_rpc_params(mock_supabase)
        hashes = [v["token_hash"] for v in params["p_vendors"]]
        assert all(h for h in hashes), "every vendor must have a token hash"
        assert len(set(hashes)) == len(hashes), "token hashes must be unique"

    @pytest.mark.asyncio
    async def test_sends_one_email_per_vendor(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """An email is sent for each vendor, producing email_log entries."""
        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert mock_email_service.send_email.call_count == 3

    @pytest.mark.asyncio
    async def test_task_flip_delegated_to_rpc(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """The draft->bidding flip happens inside the RPC (task id passed in)."""
        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        params = _create_rpc_params(mock_supabase)
        assert params["p_task_id"] == str(TASK_ID)

    @pytest.mark.asyncio
    async def test_response_includes_summary(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """Response includes bid_package_id, round_number, counts, and deadline."""
        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert "bid_package_id" in result
        assert "round_number" in result
        assert result["invitations_sent"] == 3
        assert result["invitations_failed"] == 0
        assert result["failed_vendors"] == []
        assert "deadline" in result


class TestRoundNumberAutoIncrement:
    """round_number is returned by the RPC (set by a DB trigger)."""

    @pytest.mark.asyncio
    async def test_first_bid_package_is_round_1(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """First bid package for a task should have round_number=1."""
        configure_create_rpc(mock_supabase, round_number=1)

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert result["round_number"] == 1

    @pytest.mark.asyncio
    async def test_second_bid_package_is_round_2(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """A rebid returns round_number=2 (DB trigger, surfaced through the RPC)."""
        configure_create_rpc(mock_supabase, round_number=2)

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert result["round_number"] == 2


class TestEmptyDocuments:
    """Bid package creation with no project documents is valid."""

    @pytest.mark.asyncio
    async def test_empty_project_document_ids(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        vendor_selections,
        future_deadline,
    ):
        """Creating a bid package with empty project_document_ids succeeds."""
        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": vendor_selections,
        }

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert result is not None
        assert result["invitations_sent"] == 3

        params = _create_rpc_params(mock_supabase)
        assert params["p_project_document_ids"] == []


class TestSingleVendor:
    """Minimum valid case: single vendor."""

    @pytest.mark.asyncio
    async def test_single_vendor_creates_one_invitation(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        future_deadline,
    ):
        """A single vendor in vendor_selections creates exactly one invitation."""
        from .conftest import VENDOR_CONTACT_IDS

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [str(DOC_IDS[0])],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert result["invitations_sent"] == 1
        assert mock_email_service.send_email.call_count == 1

        params = _create_rpc_params(mock_supabase)
        assert len(params["p_vendors"]) == 1
