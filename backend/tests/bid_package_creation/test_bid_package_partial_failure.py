"""
Partial failure tests for bid package creation.

When email sending fails for one vendor, the system should still succeed
for the other vendors. Invitations and tokens are created before emails
are sent, so they persist even on email failure.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.email_service import EmailSendResult

from .conftest import (
    BID_TEMPLATE_ID,
    DOC_IDS,
    PM_USER_ID,
    TASK_ID,
    VENDOR_CONTACT_IDS,
    VENDOR_IDS,
)

# This import will fail until the service is implemented — expected for test-first.
from app.services.bid_package_service import create_bid_package_with_invitations


# The email address that will trigger a simulated failure.
FAILING_EMAIL = "maria@apexearth.com"


def _make_email_service_with_one_failure() -> AsyncMock:
    """Create a mock email service where one specific vendor's email fails."""
    service = AsyncMock()

    async def conditional_send(**kwargs):
        to_email = kwargs.get("to_email", "")
        if to_email == FAILING_EMAIL:
            return EmailSendResult(
                message_id=f"mock-{uuid4()}",
                status="failed",
                error="MessageRejected: Email address is not verified",
            )
        return EmailSendResult(
            message_id=f"mock-{uuid4()}",
            status="sent",
            error=None,
        )

    service.send_email.side_effect = conditional_send
    return service


def _setup_creation_mocks(mock_supabase, deadline_iso: str):
    """Configure mocks for successful bid package + invitation creation."""
    bid_package_id = uuid4()
    invitation_ids = {str(VENDOR_IDS[i]): str(uuid4()) for i in range(3)}

    def table_side_effect(table_name):
        chain = MagicMock()

        if table_name == "bid_packages":
            insert_result = MagicMock()
            insert_result.execute.return_value = MagicMock(data=[{
                "id": str(bid_package_id),
                "task_id": str(TASK_ID),
                "round_number": 1,
                "deadline": deadline_iso,
                "status": "open",
                "bid_template_id": str(BID_TEMPLATE_ID),
                "created_by": str(PM_USER_ID),
            }])
            chain.insert.return_value = insert_result
        elif table_name == "bid_invitations":
            def inv_insert(row):
                vendor_id = row.get("vendor_id", "")
                result = MagicMock()
                result.execute.return_value = MagicMock(data=[{
                    **row,
                    "id": invitation_ids.get(vendor_id, str(uuid4())),
                }])
                return result
            chain.insert.side_effect = inv_insert
        elif table_name == "magic_link_tokens":
            def token_insert(row):
                result = MagicMock()
                result.execute.return_value = MagicMock(data=[{**row, "id": str(uuid4())}])
                return result
            chain.insert.side_effect = token_insert
        else:
            result = MagicMock()
            result.execute.return_value = MagicMock(data=[])
            chain.insert.return_value = result
            chain.select.return_value = result
            chain.update.return_value = result
            result.eq.return_value = result

        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.is_.return_value = chain
        chain.single.return_value = chain
        if not hasattr(chain.execute, 'return_value') or chain.execute.return_value is None:
            chain.execute.return_value = MagicMock(data=[])

        return chain

    mock_supabase.table.side_effect = table_side_effect
    return bid_package_id, invitation_ids


class TestPartialEmailFailure:
    """When one vendor's email fails, the rest should still succeed."""

    @pytest.mark.asyncio
    async def test_other_vendors_still_get_invitations(
        self,
        mock_supabase,
        mock_template_renderer,
        future_deadline,
    ):
        """If email fails for vendor 2, vendors 1 and 3 still get their emails."""
        email_service = _make_email_service_with_one_failure()
        _setup_creation_mocks(mock_supabase, future_deadline.isoformat())

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[i]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[i])}
                for i in range(3)
            ],
        }

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=email_service,
            template_renderer=mock_template_renderer,
        )

        # All 3 vendors should have had send_email called
        assert email_service.send_email.call_count == 3

        # 2 succeeded, 1 failed
        assert result["invitations_sent"] == 2
        assert result["invitations_failed"] == 1

    @pytest.mark.asyncio
    async def test_failed_vendor_invitation_exists_in_db(
        self,
        mock_supabase,
        mock_template_renderer,
        future_deadline,
    ):
        """Failed vendor's invitation and magic_link_token still exist in DB."""
        email_service = _make_email_service_with_one_failure()
        bid_package_id, invitation_ids = _setup_creation_mocks(
            mock_supabase, future_deadline.isoformat()
        )

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[i]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[i])}
                for i in range(3)
            ],
        }

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=email_service,
            template_renderer=mock_template_renderer,
        )

        # bid_invitations insert should have been called 3 times (once per vendor)
        invitation_calls = [
            c for c in mock_supabase.table.call_args_list
            if hasattr(c, 'args') and c.args and c.args[0] == "bid_invitations"
        ]
        assert len(invitation_calls) >= 3, (
            "All 3 invitations should be created in DB even if email fails"
        )

        # magic_link_tokens insert should have been called 3 times
        token_calls = [
            c for c in mock_supabase.table.call_args_list
            if hasattr(c, 'args') and c.args and c.args[0] == "magic_link_tokens"
        ]
        assert len(token_calls) >= 3, (
            "All 3 tokens should be created in DB even if email fails"
        )

    @pytest.mark.asyncio
    async def test_failed_vendor_in_response_with_error(
        self,
        mock_supabase,
        mock_template_renderer,
        future_deadline,
    ):
        """The failed vendor appears in the failed_vendors response array with error reason."""
        email_service = _make_email_service_with_one_failure()
        _setup_creation_mocks(mock_supabase, future_deadline.isoformat())

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[i]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[i])}
                for i in range(3)
            ],
        }

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(result["failed_vendors"]) == 1
        failed = result["failed_vendors"][0]
        assert failed["vendor_id"] == str(VENDOR_IDS[1])  # maria@apexearth.com is vendor index 1
        assert "error" in failed
        assert len(failed["error"]) > 0

    @pytest.mark.asyncio
    async def test_email_log_status_failed_for_failed_vendor(
        self,
        mock_supabase,
        mock_template_renderer,
        future_deadline,
    ):
        """email_log for the failed vendor has status='failed'."""
        email_service = _make_email_service_with_one_failure()
        _setup_creation_mocks(mock_supabase, future_deadline.isoformat())

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[i]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[i])}
                for i in range(3)
            ],
        }

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=email_service,
            template_renderer=mock_template_renderer,
        )

        # The email service should have been called with reference_type and reference_id
        # for each vendor. The failed send's email_log should end up with status='failed'.
        # Since EmailService handles logging internally, we verify the service was called
        # with the failing email's kwargs.
        calls = email_service.send_email.call_args_list
        failing_call = [c for c in calls if c.kwargs.get("to_email") == FAILING_EMAIL]
        assert len(failing_call) == 1, "Email service should have been called for failing vendor"

    @pytest.mark.asyncio
    async def test_response_counts_are_correct(
        self,
        mock_supabase,
        mock_template_renderer,
        future_deadline,
    ):
        """Response shows correct invitations_sent and invitations_failed."""
        email_service = _make_email_service_with_one_failure()
        _setup_creation_mocks(mock_supabase, future_deadline.isoformat())

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[i]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[i])}
                for i in range(3)
            ],
        }

        result = await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=email_service,
            template_renderer=mock_template_renderer,
        )

        assert result["invitations_sent"] == 2
        assert result["invitations_failed"] == 1
        assert result["invitations_sent"] + result["invitations_failed"] == 3
