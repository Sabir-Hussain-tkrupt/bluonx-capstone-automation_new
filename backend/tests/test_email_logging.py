"""
Tests for email logging — every send_email call must create a row in email_log.

Verifies that the EmailService correctly logs sends, failures, and retries
to the email_log table via the Supabase client.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.services.email_service import (
    EmailProvider,
    EmailSendResult,
    EmailService,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_provider() -> AsyncMock:
    """A mock email provider that returns success by default."""
    provider = AsyncMock(spec=EmailProvider)
    provider.send.return_value = EmailSendResult(
        message_id="ses-msg-abc123",
        status="sent",
        error=None,
    )
    return provider


@pytest.fixture()
def mock_db_client() -> MagicMock:
    """Mock Supabase client tracking all email_log operations."""
    client = MagicMock()

    # .table("email_log").insert({...}).execute()
    insert_execute = MagicMock()
    insert_execute.execute.return_value = MagicMock(
        data=[{
            "id": "11111111-2222-3333-4444-555555555555",
            "status": "queued",
            "retry_count": 0,
        }]
    )

    # .table("email_log").update({...}).eq("id", ...).execute()
    update_eq = MagicMock()
    update_eq.execute.return_value = MagicMock(data=[])
    update_mock = MagicMock()
    update_mock.eq.return_value = update_eq

    table_mock = MagicMock()
    table_mock.insert.return_value = insert_execute
    table_mock.update.return_value = update_mock

    client.table.return_value = table_mock
    return client


@pytest.fixture()
def email_service(mock_provider, mock_db_client) -> EmailService:
    return EmailService(provider=mock_provider, db_client=mock_db_client)


@pytest.fixture()
def send_kwargs() -> dict:
    """Standard send_email keyword arguments."""
    return {
        "to_email": "john@smithgrading.com",
        "subject": "Bid Invitation: Rough Grading — Sunset Ridge Phase 2",
        "html_body": "<h1>Invitation</h1>",
        "plain_text_body": "Invitation",
        "email_type": "bid_invitation",
        "recipient_type": "vendor_contact",
        "reference_type": "bid_invitations",
        "reference_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    }


# ── Log creation on send ───────────────────────────────────────────────────


class TestEmailLogCreation:
    """Every send_email call must insert a row into email_log."""

    @pytest.mark.asyncio
    async def test_creates_email_log_row(self, email_service, mock_db_client, send_kwargs):
        await email_service.send_email(**send_kwargs)
        mock_db_client.table.assert_any_call("email_log")
        mock_db_client.table("email_log").insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_has_recipient_email(self, email_service, mock_db_client, send_kwargs):
        await email_service.send_email(**send_kwargs)
        insert_call = mock_db_client.table("email_log").insert.call_args
        row = insert_call[0][0] if insert_call[0] else insert_call[1].get("json", {})
        assert row["recipient_email"] == "john@smithgrading.com"

    @pytest.mark.asyncio
    async def test_log_has_recipient_type(self, email_service, mock_db_client, send_kwargs):
        await email_service.send_email(**send_kwargs)
        insert_call = mock_db_client.table("email_log").insert.call_args
        row = insert_call[0][0] if insert_call[0] else insert_call[1].get("json", {})
        assert row["recipient_type"] == "vendor_contact"

    @pytest.mark.asyncio
    async def test_log_has_email_type(self, email_service, mock_db_client, send_kwargs):
        await email_service.send_email(**send_kwargs)
        insert_call = mock_db_client.table("email_log").insert.call_args
        row = insert_call[0][0] if insert_call[0] else insert_call[1].get("json", {})
        assert row["email_type"] == "bid_invitation"

    @pytest.mark.asyncio
    async def test_log_has_subject(self, email_service, mock_db_client, send_kwargs):
        await email_service.send_email(**send_kwargs)
        insert_call = mock_db_client.table("email_log").insert.call_args
        row = insert_call[0][0] if insert_call[0] else insert_call[1].get("json", {})
        assert row["subject"] == send_kwargs["subject"]

    @pytest.mark.asyncio
    async def test_log_has_reference_fields(self, email_service, mock_db_client, send_kwargs):
        await email_service.send_email(**send_kwargs)
        insert_call = mock_db_client.table("email_log").insert.call_args
        row = insert_call[0][0] if insert_call[0] else insert_call[1].get("json", {})
        assert row["reference_type"] == "bid_invitations"
        assert row["reference_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


# ── Status logging ──────────────────────────────────────────────────────────


class TestEmailLogStatus:
    """Tests that the email_log status is updated correctly after sending."""

    @pytest.mark.asyncio
    async def test_successful_send_logs_status_sent(
        self, email_service, mock_db_client, send_kwargs
    ):
        """After successful send, email_log row is updated to status='sent'."""
        await email_service.send_email(**send_kwargs)
        # The service should update the log row with status='sent' and sent_at
        update_mock = mock_db_client.table("email_log").update
        update_mock.assert_called()
        update_data = update_mock.call_args[0][0]
        assert update_data["status"] == "sent"
        assert "sent_at" in update_data

    @pytest.mark.asyncio
    async def test_failed_send_logs_status_failed(
        self, mock_provider, mock_db_client, send_kwargs
    ):
        """On permanent failure, email_log should have status='failed' and error_message."""
        mock_provider.send.return_value = EmailSendResult(
            message_id="", status="failed", error="MessageRejected"
        )
        service = EmailService(provider=mock_provider, db_client=mock_db_client)
        await service.send_email(**send_kwargs)

        update_mock = mock_db_client.table("email_log").update
        update_mock.assert_called()
        update_data = update_mock.call_args[0][0]
        assert update_data["status"] == "failed"
        assert update_data["error_message"] is not None
        assert "MessageRejected" in update_data["error_message"]

    @pytest.mark.asyncio
    async def test_retry_count_incremented(self, mock_provider, mock_db_client, send_kwargs):
        """retry_count in email_log should reflect the number of retry attempts."""
        # Fail twice, succeed on third
        mock_provider.send.side_effect = [
            EmailSendResult(message_id="", status="failed", error="ServiceUnavailable"),
            EmailSendResult(message_id="", status="failed", error="Throttling"),
            EmailSendResult(message_id="msg-ok", status="sent", error=None),
        ]
        service = EmailService(provider=mock_provider, db_client=mock_db_client)
        await service.send_email(**send_kwargs)

        # The final update should include retry_count=2 (retried twice)
        update_mock = mock_db_client.table("email_log").update
        # Find the final update call
        final_update = update_mock.call_args[0][0]
        assert final_update.get("retry_count", 0) >= 2

    @pytest.mark.asyncio
    async def test_log_without_optional_reference_fields(
        self, email_service, mock_db_client
    ):
        """send_email without reference_type/reference_id still logs correctly."""
        await email_service.send_email(
            to_email="someone@example.com",
            subject="General notification",
            html_body="<p>Hi</p>",
            plain_text_body="Hi",
            email_type="general",
            recipient_type="user",
        )
        insert_call = mock_db_client.table("email_log").insert.call_args
        row = insert_call[0][0] if insert_call[0] else insert_call[1].get("json", {})
        assert row["email_type"] == "general"
        assert row["recipient_type"] == "user"
        # reference fields should be None or not present
        assert row.get("reference_type") is None
        assert row.get("reference_id") is None
