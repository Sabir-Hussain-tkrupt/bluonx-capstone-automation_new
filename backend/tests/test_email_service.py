"""
Tests for the EmailService interface — send_email, retry logic, rate limiting.

These tests define the contract the EmailService implementation must satisfy.
All tests are expected to FAIL until the implementation is built.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.email_service import (
    Attachment,
    EmailPayload,
    EmailProvider,
    EmailSendResult,
    EmailService,
    MockEmailProvider,
    SESEmailProvider,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_provider() -> AsyncMock:
    """A mock email provider that returns success by default."""
    provider = AsyncMock(spec=EmailProvider)
    provider.send.return_value = EmailSendResult(
        message_id="mock-msg-001",
        status="sent",
        error=None,
    )
    return provider


@pytest.fixture()
def mock_db_client() -> MagicMock:
    """Mock Supabase client for email_log operations."""
    client = MagicMock()
    # Mock the .table("email_log").insert(...).execute() chain
    execute_mock = MagicMock()
    execute_mock.execute.return_value = MagicMock(
        data=[{"id": "fake-log-id", "status": "queued"}]
    )
    insert_mock = MagicMock()
    insert_mock.insert.return_value = execute_mock
    # Also mock .table("email_log").update(...).eq(...).execute()
    update_chain = MagicMock()
    update_chain.eq.return_value = MagicMock()
    update_chain.eq.return_value.execute.return_value = MagicMock(data=[])
    insert_mock.update.return_value = update_chain
    client.table.return_value = insert_mock
    return client


@pytest.fixture()
def email_service(mock_provider, mock_db_client) -> EmailService:
    """EmailService with a mock provider and mock DB client."""
    return EmailService(provider=mock_provider, db_client=mock_db_client)


@pytest.fixture()
def sample_email_kwargs() -> dict:
    """Standard keyword arguments for send_email calls."""
    return {
        "to_email": "vendor@example.com",
        "subject": "Bid Invitation: Rough Grading — Sunset Ridge Phase 2",
        "html_body": "<h1>You're Invited</h1><p>Please submit your bid.</p>",
        "plain_text_body": "You're Invited\n\nPlease submit your bid.",
        "email_type": "bid_invitation",
        "recipient_type": "vendor_contact",
        "reference_type": "bid_invitations",
        "reference_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    }


# ── Basic send_email contract ──────────────────────────────────────────────


class TestSendEmail:
    """Tests for the basic send_email interface."""

    @pytest.mark.asyncio
    async def test_returns_email_send_result(self, email_service, sample_email_kwargs):
        result = await email_service.send_email(**sample_email_kwargs)
        assert isinstance(result, EmailSendResult)

    @pytest.mark.asyncio
    async def test_result_has_message_id(self, email_service, sample_email_kwargs):
        result = await email_service.send_email(**sample_email_kwargs)
        assert result.message_id
        assert isinstance(result.message_id, str)

    @pytest.mark.asyncio
    async def test_result_status_is_sent(self, email_service, sample_email_kwargs):
        result = await email_service.send_email(**sample_email_kwargs)
        assert result.status == "sent"

    @pytest.mark.asyncio
    async def test_result_error_is_none_on_success(self, email_service, sample_email_kwargs):
        result = await email_service.send_email(**sample_email_kwargs)
        assert result.error is None

    @pytest.mark.asyncio
    async def test_invalid_email_raises_or_returns_error(self, email_service):
        """send_email with clearly invalid email should raise ValueError or return error."""
        try:
            result = await email_service.send_email(
                to_email="not-an-email",
                subject="Test",
                html_body="<p>Test</p>",
                plain_text_body="Test",
            )
            # If it returns instead of raising, status should be 'failed'
            assert result.status == "failed"
            assert result.error is not None
        except ValueError:
            pass  # Also acceptable

    @pytest.mark.asyncio
    async def test_empty_email_raises_or_returns_error(self, email_service):
        """send_email with empty email string should fail."""
        try:
            result = await email_service.send_email(
                to_email="",
                subject="Test",
                html_body="<p>Test</p>",
                plain_text_body="Test",
            )
            assert result.status == "failed"
        except ValueError:
            pass


# ── Default from_email ──────────────────────────────────────────────────────


class TestDefaultFromEmail:
    """Tests that from_email defaults to configured SES_FROM_EMAIL."""

    @pytest.mark.asyncio
    async def test_from_email_defaults_when_not_provided(
        self, email_service, mock_provider, sample_email_kwargs
    ):
        """When from_email is not passed, the provider receives the configured default."""
        await email_service.send_email(**sample_email_kwargs)
        mock_provider.send.assert_called_once()
        payload: EmailPayload = mock_provider.send.call_args[0][0]
        assert payload.from_email is not None
        assert "@" in payload.from_email

    @pytest.mark.asyncio
    async def test_from_email_uses_explicit_value(
        self, email_service, mock_provider, sample_email_kwargs
    ):
        """When from_email is explicitly provided, it takes precedence."""
        sample_email_kwargs["from_email"] = "custom@bluonx.com"
        await email_service.send_email(**sample_email_kwargs)
        mock_provider.send.assert_called_once()
        payload: EmailPayload = mock_provider.send.call_args[0][0]
        assert payload.from_email == "custom@bluonx.com"

    @pytest.mark.asyncio
    async def test_reply_to_is_passed_through(
        self, email_service, mock_provider, sample_email_kwargs
    ):
        sample_email_kwargs["reply_to"] = "pm@bluonx.com"
        await email_service.send_email(**sample_email_kwargs)
        payload: EmailPayload = mock_provider.send.call_args[0][0]
        assert payload.reply_to == "pm@bluonx.com"

    @pytest.mark.asyncio
    async def test_attachments_are_passed_through(
        self, email_service, mock_provider, sample_email_kwargs
    ):
        attachment = Attachment(
            filename="scope.pdf",
            content=b"%PDF-fake-content",
            content_type="application/pdf",
        )
        sample_email_kwargs["attachments"] = [attachment]
        await email_service.send_email(**sample_email_kwargs)
        payload: EmailPayload = mock_provider.send.call_args[0][0]
        assert len(payload.attachments) == 1
        assert payload.attachments[0].filename == "scope.pdf"


# ── Retry logic ─────────────────────────────────────────────────────────────


class TestRetryLogic:
    """Tests that transient failures trigger retries and permanent failures do not."""

    @pytest.mark.asyncio
    async def test_retries_on_transient_failure(
        self, mock_provider, mock_db_client, sample_email_kwargs
    ):
        """Service retries up to 3 times on transient provider failure."""
        # First 2 calls fail transiently, 3rd succeeds
        mock_provider.send.side_effect = [
            EmailSendResult(message_id="", status="failed", error="ServiceUnavailable"),
            EmailSendResult(message_id="", status="failed", error="Throttling"),
            EmailSendResult(message_id="msg-003", status="sent", error=None),
        ]
        service = EmailService(provider=mock_provider, db_client=mock_db_client)
        result = await service.send_email(**sample_email_kwargs)
        assert result.status == "sent"
        assert result.message_id == "msg-003"
        assert mock_provider.send.call_count == 3

    @pytest.mark.asyncio
    async def test_gives_up_after_max_retries(
        self, mock_provider, mock_db_client, sample_email_kwargs
    ):
        """After 3 failed attempts, service returns failure."""
        mock_provider.send.return_value = EmailSendResult(
            message_id="", status="failed", error="ServiceUnavailable"
        )
        service = EmailService(provider=mock_provider, db_client=mock_db_client)
        result = await service.send_email(**sample_email_kwargs)
        assert result.status == "failed"
        assert result.error is not None
        assert mock_provider.send.call_count == 3

    @pytest.mark.asyncio
    async def test_permanent_failure_does_not_retry(
        self, mock_provider, mock_db_client, sample_email_kwargs
    ):
        """Permanent failures (e.g., invalid address) should NOT retry."""
        mock_provider.send.return_value = EmailSendResult(
            message_id="", status="failed", error="MessageRejected"
        )
        service = EmailService(provider=mock_provider, db_client=mock_db_client)
        result = await service.send_email(**sample_email_kwargs)
        assert result.status == "failed"
        # Should only call provider once — no retries for permanent errors
        assert mock_provider.send.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_use_exponential_backoff(
        self, mock_provider, mock_db_client, sample_email_kwargs
    ):
        """Retries should wait with exponential backoff (1s, 4s, 16s)."""
        mock_provider.send.return_value = EmailSendResult(
            message_id="", status="failed", error="ServiceUnavailable"
        )
        service = EmailService(provider=mock_provider, db_client=mock_db_client)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await service.send_email(**sample_email_kwargs)
            # Should have slept twice (between attempt 1→2 and 2→3)
            assert mock_sleep.call_count == 2
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            # Expect exponential: 1s, 4s (base=1, factor=4^n or similar)
            assert delays[0] >= 1
            assert delays[1] > delays[0]


# ── Rate limiting ───────────────────────────────────────────────────────────


class TestRateLimiting:
    """Tests that the service respects configurable send rate."""

    @pytest.mark.asyncio
    async def test_send_bulk_emails_returns_list(
        self, mock_provider, mock_db_client
    ):
        """send_bulk_emails returns a list of EmailSendResult."""
        service = EmailService(provider=mock_provider, db_client=mock_db_client)
        emails = [
            EmailPayload(
                to_email=f"vendor{i}@example.com",
                subject="Bid Invitation",
                html_body="<p>Hello</p>",
                plain_text_body="Hello",
            )
            for i in range(5)
        ]
        results = await service.send_bulk_emails(emails)
        assert isinstance(results, list)
        assert len(results) == 5
        assert all(isinstance(r, EmailSendResult) for r in results)

    @pytest.mark.asyncio
    async def test_send_bulk_respects_rate_limit(
        self, mock_provider, mock_db_client
    ):
        """Bulk sends should not exceed the configured rate limit."""
        service = EmailService(provider=mock_provider, db_client=mock_db_client)
        emails = [
            EmailPayload(
                to_email=f"vendor{i}@example.com",
                subject="Bid Invitation",
                html_body="<p>Hello</p>",
                plain_text_body="Hello",
            )
            for i in range(3)
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await service.send_bulk_emails(emails)
            # With rate limiting, there should be delays between sends
            assert mock_sleep.call_count >= 2  # N-1 delays for N emails

    @pytest.mark.asyncio
    async def test_send_bulk_empty_list(self, mock_provider, mock_db_client):
        """send_bulk_emails with empty list returns empty list."""
        service = EmailService(provider=mock_provider, db_client=mock_db_client)
        results = await service.send_bulk_emails([])
        assert results == []


# ── Provider protocol compliance ────────────────────────────────────────────


class TestProviderProtocol:
    """Tests that providers implement the EmailProvider protocol."""

    def test_mock_provider_implements_protocol(self):
        assert isinstance(MockEmailProvider(), EmailProvider)

    def test_ses_provider_implements_protocol(self):
        assert isinstance(SESEmailProvider(), EmailProvider)
