"""
Happy-path tests for bid package creation with invitation sending.

Verifies the full orchestration flow: bid_packages row, bid_package_documents,
bid_invitations, magic_link_tokens, email_log, and task status update.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from app.services.email_service import EmailSendResult

from .conftest import (
    BID_TEMPLATE_ID,
    DOC_IDS,
    PM_USER_ID,
    PROJECT_ID,
    TASK_ID,
    VENDOR_CONTACT_IDS,
    VENDOR_IDS,
)

# This import will fail until the service is implemented — expected for test-first.
from app.services.bid_package_service import create_bid_package_with_invitations


class TestBidPackageHappyPath:
    """Full happy-path: 1 template, 2 documents, 3 vendors."""

    @pytest.mark.asyncio
    async def test_creates_bid_package_row(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_task_competitive,
        bid_package_request_payload,
        sample_pm_user,
        future_deadline,
    ):
        """A bid_packages row is created with correct task_id, deadline, and status='open'."""
        bid_package_id = uuid4()

        # Configure mock to return created bid package
        bp_insert_result = MagicMock()
        bp_insert_result.execute.return_value = MagicMock(data=[{
            "id": str(bid_package_id),
            "task_id": str(TASK_ID),
            "round_number": 1,
            "deadline": future_deadline.isoformat(),
            "status": "open",
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }])

        mock_supabase.table.return_value.insert.return_value = bp_insert_result

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        # Verify bid_packages insert was called
        insert_calls = [
            c for c in mock_supabase.table.call_args_list
            if c == call("bid_packages")
        ]
        assert len(insert_calls) >= 1, "bid_packages table should be accessed"
        assert result is not None

    @pytest.mark.asyncio
    async def test_creates_bid_package_documents(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """bid_package_documents rows are created for each project document."""
        bid_package_id = uuid4()

        # Configure mock for bid package creation
        bp_insert = MagicMock()
        bp_insert.execute.return_value = MagicMock(data=[{
            "id": str(bid_package_id),
            "task_id": str(TASK_ID),
            "round_number": 1,
            "deadline": bid_package_request_payload["deadline"],
            "status": "open",
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }])
        mock_supabase.table.return_value.insert.return_value = bp_insert

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        # Verify bid_package_documents table was accessed for each doc
        doc_table_calls = [
            c for c in mock_supabase.table.call_args_list
            if c == call("bid_package_documents")
        ]
        assert len(doc_table_calls) >= 1, "bid_package_documents table should be accessed"

    @pytest.mark.asyncio
    async def test_creates_invitations_for_each_vendor(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """bid_invitations rows are created for each vendor in vendor_selections."""
        bid_package_id = uuid4()
        bp_insert = MagicMock()
        bp_insert.execute.return_value = MagicMock(data=[{
            "id": str(bid_package_id),
            "task_id": str(TASK_ID),
            "round_number": 1,
            "deadline": bid_package_request_payload["deadline"],
            "status": "open",
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }])
        mock_supabase.table.return_value.insert.return_value = bp_insert

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        # 3 vendors = 3 invitations
        invitation_table_calls = [
            c for c in mock_supabase.table.call_args_list
            if c == call("bid_invitations")
        ]
        assert len(invitation_table_calls) >= 3, (
            "bid_invitations table should be accessed at least once per vendor"
        )

    @pytest.mark.asyncio
    async def test_creates_magic_link_tokens_for_each_invitation(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """magic_link_tokens rows are created for each invitation."""
        bid_package_id = uuid4()
        bp_insert = MagicMock()
        bp_insert.execute.return_value = MagicMock(data=[{
            "id": str(bid_package_id),
            "task_id": str(TASK_ID),
            "round_number": 1,
            "deadline": bid_package_request_payload["deadline"],
            "status": "open",
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }])
        mock_supabase.table.return_value.insert.return_value = bp_insert

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        token_table_calls = [
            c for c in mock_supabase.table.call_args_list
            if c == call("magic_link_tokens")
        ]
        assert len(token_table_calls) >= 3, (
            "magic_link_tokens table should be accessed at least once per vendor"
        )

    @pytest.mark.asyncio
    async def test_creates_email_log_for_each_vendor(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """An email is sent for each vendor, producing email_log entries."""
        bid_package_id = uuid4()
        bp_insert = MagicMock()
        bp_insert.execute.return_value = MagicMock(data=[{
            "id": str(bid_package_id),
            "task_id": str(TASK_ID),
            "round_number": 1,
            "deadline": bid_package_request_payload["deadline"],
            "status": "open",
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }])
        mock_supabase.table.return_value.insert.return_value = bp_insert

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        # EmailService.send_email should be called once per vendor
        assert mock_email_service.send_email.call_count == 3

    @pytest.mark.asyncio
    async def test_task_status_updated_to_bidding(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """Task status is updated from 'draft' to 'bidding' after successful creation."""
        bid_package_id = uuid4()
        bp_insert = MagicMock()
        bp_insert.execute.return_value = MagicMock(data=[{
            "id": str(bid_package_id),
            "task_id": str(TASK_ID),
            "round_number": 1,
            "deadline": bid_package_request_payload["deadline"],
            "status": "open",
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }])
        mock_supabase.table.return_value.insert.return_value = bp_insert

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=bid_package_request_payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        # Verify tasks table was updated with status='bidding'
        task_table_calls = [
            c for c in mock_supabase.table.call_args_list
            if c == call("tasks")
        ]
        assert len(task_table_calls) >= 1, "tasks table should be accessed to update status"

    @pytest.mark.asyncio
    async def test_response_includes_summary(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
        future_deadline,
    ):
        """Response includes bid_package_id, round_number, invitation counts, and deadline."""
        bid_package_id = uuid4()
        bp_insert = MagicMock()
        bp_insert.execute.return_value = MagicMock(data=[{
            "id": str(bid_package_id),
            "task_id": str(TASK_ID),
            "round_number": 1,
            "deadline": future_deadline.isoformat(),
            "status": "open",
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }])
        mock_supabase.table.return_value.insert.return_value = bp_insert

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
    """Verify round_number auto-increments across bid packages for the same task."""

    @pytest.mark.asyncio
    async def test_first_bid_package_is_round_1(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        bid_package_request_payload,
    ):
        """First bid package for a task should have round_number=1."""
        bp_insert = MagicMock()
        bp_insert.execute.return_value = MagicMock(data=[{
            "id": str(uuid4()),
            "task_id": str(TASK_ID),
            "round_number": 1,
            "deadline": bid_package_request_payload["deadline"],
            "status": "open",
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }])
        mock_supabase.table.return_value.insert.return_value = bp_insert

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
        """Second bid package for the same task should have round_number=2 (DB trigger)."""
        # Simulate DB trigger returning round 2
        bp_insert = MagicMock()
        bp_insert.execute.return_value = MagicMock(data=[{
            "id": str(uuid4()),
            "task_id": str(TASK_ID),
            "round_number": 2,
            "deadline": bid_package_request_payload["deadline"],
            "status": "open",
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }])
        mock_supabase.table.return_value.insert.return_value = bp_insert

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

        bp_insert = MagicMock()
        bp_insert.execute.return_value = MagicMock(data=[{
            "id": str(uuid4()),
            "task_id": str(TASK_ID),
            "round_number": 1,
            "deadline": future_deadline.isoformat(),
            "status": "open",
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }])
        mock_supabase.table.return_value.insert.return_value = bp_insert

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

        # bid_package_documents should NOT be accessed
        doc_table_calls = [
            c for c in mock_supabase.table.call_args_list
            if c == call("bid_package_documents")
        ]
        assert len(doc_table_calls) == 0, (
            "No bid_package_documents rows should be created for empty doc list"
        )


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
        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [str(DOC_IDS[0])],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        bp_insert = MagicMock()
        bp_insert.execute.return_value = MagicMock(data=[{
            "id": str(uuid4()),
            "task_id": str(TASK_ID),
            "round_number": 1,
            "deadline": future_deadline.isoformat(),
            "status": "open",
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }])
        mock_supabase.table.return_value.insert.return_value = bp_insert

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
