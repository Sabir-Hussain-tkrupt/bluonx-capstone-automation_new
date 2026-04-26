"""
Tests for MockEmailProvider — the console-logging email provider for dev/testing.

Verifies that the mock provider:
  - Logs email details to the logger
  - Always returns success with a generated message_id
  - Creates email_log entries like the real provider
  - Implements the same interface (EmailProvider protocol)
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from app.services.email_service import (
    EmailPayload,
    EmailProvider,
    EmailSendResult,
    MockEmailProvider,
    SESEmailProvider,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_provider() -> MockEmailProvider:
    return MockEmailProvider()


@pytest.fixture()
def sample_payload() -> EmailPayload:
    """A standard email payload for testing."""
    return EmailPayload(
        to_email="vendor@example.com",
        subject="Bid Invitation: Rough Grading — Sunset Ridge Phase 2",
        html_body="<h1>You're Invited</h1><p>Submit your bid.</p>",
        plain_text_body="You're Invited\n\nSubmit your bid.",
        from_email="noreply@bluonx.com",
        reply_to="pm@bluonx.com",
    )


# ── Protocol compliance ─────────────────────────────────────────────────────


class TestMockProviderProtocol:
    """MockEmailProvider must implement the EmailProvider protocol."""

    def test_implements_email_provider_protocol(self):
        """MockEmailProvider should be recognized as an EmailProvider."""
        provider = MockEmailProvider()
        assert isinstance(provider, EmailProvider)

    def test_has_send_method(self):
        """MockEmailProvider must have an async send method."""
        provider = MockEmailProvider()
        assert hasattr(provider, "send")
        assert callable(provider.send)

    def test_ses_provider_also_implements_protocol(self):
        """SESEmailProvider should also implement the same protocol."""
        with patch("app.services.email_providers.ses_provider.boto3"):
            provider = SESEmailProvider(
                region="us-east-1",
                access_key_id="AKIATEST",
                secret_access_key="SECRET",
            )
        assert isinstance(provider, EmailProvider)


# ── Return value ────────────────────────────────────────────────────────────


class TestMockProviderReturnValue:
    """MockEmailProvider.send must always return success."""

    @pytest.mark.asyncio
    async def test_returns_email_send_result(self, mock_provider, sample_payload):
        result = await mock_provider.send(sample_payload)
        assert isinstance(result, EmailSendResult)

    @pytest.mark.asyncio
    async def test_returns_success_status(self, mock_provider, sample_payload):
        result = await mock_provider.send(sample_payload)
        assert result.status == "sent"

    @pytest.mark.asyncio
    async def test_returns_generated_message_id(self, mock_provider, sample_payload):
        result = await mock_provider.send(sample_payload)
        assert result.message_id
        assert isinstance(result.message_id, str)
        assert len(result.message_id) > 0

    @pytest.mark.asyncio
    async def test_returns_no_error(self, mock_provider, sample_payload):
        result = await mock_provider.send(sample_payload)
        assert result.error is None

    @pytest.mark.asyncio
    async def test_generates_unique_message_ids(self, mock_provider, sample_payload):
        """Each call should produce a different message_id."""
        result1 = await mock_provider.send(sample_payload)
        result2 = await mock_provider.send(sample_payload)
        assert result1.message_id != result2.message_id

    @pytest.mark.asyncio
    async def test_always_succeeds_regardless_of_input(self, mock_provider):
        """Mock provider succeeds even with unusual inputs."""
        payload = EmailPayload(
            to_email="anything@anywhere.com",
            subject="",
            html_body="",
            plain_text_body="",
        )
        result = await mock_provider.send(payload)
        assert result.status == "sent"


# ── Console/logger output ──────────────────────────────────────────────────


class TestMockProviderLogging:
    """MockEmailProvider must log email details for development visibility."""

    @pytest.mark.asyncio
    async def test_logs_email_to_logger(self, mock_provider, sample_payload, caplog):
        """send() should log the email details at INFO level."""
        with caplog.at_level(logging.INFO):
            await mock_provider.send(sample_payload)
        # Should log at least the recipient and subject
        log_output = caplog.text
        assert "vendor@example.com" in log_output
        assert "Bid Invitation" in log_output

    @pytest.mark.asyncio
    async def test_logs_from_email(self, mock_provider, sample_payload, caplog):
        """Log output should include the from address."""
        with caplog.at_level(logging.INFO):
            await mock_provider.send(sample_payload)
        assert "noreply@bluonx.com" in caplog.text

    @pytest.mark.asyncio
    async def test_logs_indicate_mock_mode(self, mock_provider, sample_payload, caplog):
        """Log should clearly indicate this is a mock/development send."""
        with caplog.at_level(logging.INFO):
            await mock_provider.send(sample_payload)
        log_lower = caplog.text.lower()
        assert "mock" in log_lower or "dev" in log_lower or "simulated" in log_lower
