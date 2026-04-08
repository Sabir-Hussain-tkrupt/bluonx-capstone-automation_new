"""
Unit tests for SESEmailProvider — mocked boto3, no real AWS calls.

Verifies that:
  - SESEmailProvider can be instantiated with credentials
  - send() constructs the correct SES v2 API payload
  - Successful responses are mapped to EmailSendResult(status="sent")
  - Transient errors (Throttling) return retryable error strings
  - Permanent errors (MessageRejected) return non-retryable error strings
  - The factory function selects the right provider based on config
"""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services.email_service import (
    EmailPayload,
    EmailProvider,
    EmailSendResult,
    create_email_provider,
)
from app.services.email_providers.ses_provider import SESEmailProvider


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_boto3_client() -> MagicMock:
    """A mock boto3 SES v2 client."""
    client = MagicMock()
    client.send_email.return_value = {"MessageId": "ses-real-msg-001"}
    return client


@pytest.fixture()
def ses_provider(mock_boto3_client) -> SESEmailProvider:
    """SESEmailProvider with a mocked boto3 client."""
    with patch("app.services.email_providers.ses_provider.boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_boto3_client
        provider = SESEmailProvider(
            region="us-east-1",
            access_key_id="AKIATEST123",
            secret_access_key="fakesecretkey",
        )
    # Replace the internal client with our mock
    provider._client = mock_boto3_client
    return provider


@pytest.fixture()
def sample_payload() -> EmailPayload:
    """Standard email payload for testing."""
    return EmailPayload(
        to_email="vendor@example.com",
        subject="Bid Invitation: Rough Grading — Sunset Ridge Phase 2",
        html_body="<h1>You're Invited</h1><p>Submit your bid.</p>",
        plain_text_body="You're Invited\n\nSubmit your bid.",
        from_email="noreply@bluonx.com",
        reply_to="pm@bluonx.com",
    )


def _make_client_error(code: str, message: str = "Test error") -> ClientError:
    """Helper to create a botocore ClientError."""
    return ClientError(
        error_response={"Error": {"Code": code, "Message": message}},
        operation_name="SendEmail",
    )


# ── Protocol compliance ─────────────────────────────────────────────────────


class TestSESProviderProtocol:
    """SESEmailProvider must implement the EmailProvider protocol."""

    def test_implements_protocol(self, ses_provider):
        assert isinstance(ses_provider, EmailProvider)

    def test_has_send_method(self, ses_provider):
        assert hasattr(ses_provider, "send")
        assert callable(ses_provider.send)


# ── Instantiation ───────────────────────────────────────────────────────────


class TestSESProviderInit:
    """SESEmailProvider initialisation with credentials."""

    def test_creates_boto3_client_with_credentials(self):
        with patch("app.services.email_providers.ses_provider.boto3") as mock_boto3:
            SESEmailProvider(
                region="eu-west-1",
                access_key_id="AKIATEST",
                secret_access_key="SECRET",
            )
            mock_boto3.client.assert_called_once_with(
                "sesv2",
                region_name="eu-west-1",
                aws_access_key_id="AKIATEST",
                aws_secret_access_key="SECRET",
            )


# ── Successful send ─────────────────────────────────────────────────────────


class TestSESProviderSendSuccess:
    """Successful SES send maps correctly to EmailSendResult."""

    @pytest.mark.asyncio
    async def test_returns_email_send_result(self, ses_provider, sample_payload):
        result = await ses_provider.send(sample_payload)
        assert isinstance(result, EmailSendResult)

    @pytest.mark.asyncio
    async def test_status_is_sent(self, ses_provider, sample_payload):
        result = await ses_provider.send(sample_payload)
        assert result.status == "sent"

    @pytest.mark.asyncio
    async def test_message_id_from_response(self, ses_provider, sample_payload):
        result = await ses_provider.send(sample_payload)
        assert result.message_id == "ses-real-msg-001"

    @pytest.mark.asyncio
    async def test_error_is_none(self, ses_provider, sample_payload):
        result = await ses_provider.send(sample_payload)
        assert result.error is None


# ── API payload structure ───────────────────────────────────────────────────


class TestSESAPIPayload:
    """Verify the SES v2 send_email call has the correct structure."""

    @pytest.mark.asyncio
    async def test_from_email(self, ses_provider, mock_boto3_client, sample_payload):
        await ses_provider.send(sample_payload)
        call_kwargs = mock_boto3_client.send_email.call_args[1]
        assert call_kwargs["FromEmailAddress"] == "noreply@bluonx.com"

    @pytest.mark.asyncio
    async def test_to_email(self, ses_provider, mock_boto3_client, sample_payload):
        await ses_provider.send(sample_payload)
        call_kwargs = mock_boto3_client.send_email.call_args[1]
        assert call_kwargs["Destination"]["ToAddresses"] == ["vendor@example.com"]

    @pytest.mark.asyncio
    async def test_subject(self, ses_provider, mock_boto3_client, sample_payload):
        await ses_provider.send(sample_payload)
        call_kwargs = mock_boto3_client.send_email.call_args[1]
        subject = call_kwargs["Content"]["Simple"]["Subject"]
        assert subject["Data"] == sample_payload.subject
        assert subject["Charset"] == "UTF-8"

    @pytest.mark.asyncio
    async def test_html_body(self, ses_provider, mock_boto3_client, sample_payload):
        await ses_provider.send(sample_payload)
        call_kwargs = mock_boto3_client.send_email.call_args[1]
        html = call_kwargs["Content"]["Simple"]["Body"]["Html"]
        assert html["Data"] == sample_payload.html_body
        assert html["Charset"] == "UTF-8"

    @pytest.mark.asyncio
    async def test_text_body(self, ses_provider, mock_boto3_client, sample_payload):
        await ses_provider.send(sample_payload)
        call_kwargs = mock_boto3_client.send_email.call_args[1]
        text = call_kwargs["Content"]["Simple"]["Body"]["Text"]
        assert text["Data"] == sample_payload.plain_text_body

    @pytest.mark.asyncio
    async def test_reply_to(self, ses_provider, mock_boto3_client, sample_payload):
        await ses_provider.send(sample_payload)
        call_kwargs = mock_boto3_client.send_email.call_args[1]
        assert call_kwargs["ReplyToAddresses"] == ["pm@bluonx.com"]

    @pytest.mark.asyncio
    async def test_no_reply_to_when_none(self, ses_provider, mock_boto3_client):
        payload = EmailPayload(
            to_email="test@example.com",
            subject="Test",
            html_body="<p>Test</p>",
            plain_text_body="Test",
            from_email="noreply@bluonx.com",
            reply_to=None,
        )
        await ses_provider.send(payload)
        call_kwargs = mock_boto3_client.send_email.call_args[1]
        assert "ReplyToAddresses" not in call_kwargs


# ── Transient errors (retryable) ────────────────────────────────────────────


class TestSESTransientErrors:
    """Transient SES errors should return error strings the retry logic recognises."""

    @pytest.mark.asyncio
    async def test_throttling_returns_retryable_error(self, ses_provider, mock_boto3_client, sample_payload):
        mock_boto3_client.send_email.side_effect = _make_client_error("Throttling")
        result = await ses_provider.send(sample_payload)
        assert result.status == "failed"
        assert result.error == "Throttling"

    @pytest.mark.asyncio
    async def test_service_unavailable_returns_retryable_error(self, ses_provider, mock_boto3_client, sample_payload):
        mock_boto3_client.send_email.side_effect = _make_client_error("ServiceUnavailable")
        result = await ses_provider.send(sample_payload)
        assert result.status == "failed"
        assert result.error == "ServiceUnavailable"

    @pytest.mark.asyncio
    async def test_too_many_requests_returns_retryable_error(self, ses_provider, mock_boto3_client, sample_payload):
        mock_boto3_client.send_email.side_effect = _make_client_error("TooManyRequestsException")
        result = await ses_provider.send(sample_payload)
        assert result.status == "failed"
        assert result.error == "TooManyRequestsException"


# ── Permanent errors (not retryable) ────────────────────────────────────────


class TestSESPermanentErrors:
    """Permanent SES errors should contain the error code so retry logic skips them."""

    @pytest.mark.asyncio
    async def test_message_rejected(self, ses_provider, mock_boto3_client, sample_payload):
        mock_boto3_client.send_email.side_effect = _make_client_error(
            "MessageRejected", "Email address is not verified."
        )
        result = await ses_provider.send(sample_payload)
        assert result.status == "failed"
        assert "MessageRejected" in result.error

    @pytest.mark.asyncio
    async def test_account_sending_paused(self, ses_provider, mock_boto3_client, sample_payload):
        mock_boto3_client.send_email.side_effect = _make_client_error(
            "AccountSendingPausedException", "Account paused."
        )
        result = await ses_provider.send(sample_payload)
        assert result.status == "failed"
        assert "AccountSendingPausedException" in result.error

    @pytest.mark.asyncio
    async def test_domain_not_verified(self, ses_provider, mock_boto3_client, sample_payload):
        mock_boto3_client.send_email.side_effect = _make_client_error(
            "MailFromDomainNotVerifiedException", "Domain not verified."
        )
        result = await ses_provider.send(sample_payload)
        assert result.status == "failed"
        assert "MailFromDomainNotVerifiedException" in result.error


# ── Unexpected errors ───────────────────────────────────────────────────────


class TestSESUnexpectedErrors:
    """Unexpected exceptions should be wrapped as transient errors."""

    @pytest.mark.asyncio
    async def test_generic_exception_is_transient(self, ses_provider, mock_boto3_client, sample_payload):
        mock_boto3_client.send_email.side_effect = ConnectionError("network down")
        result = await ses_provider.send(sample_payload)
        assert result.status == "failed"
        assert "ServiceUnavailable" in result.error


# ── Factory function ────────────────────────────────────────────────────────


class TestCreateEmailProvider:
    """create_email_provider() selects the right provider based on config."""

    def test_mock_provider_by_default(self):
        from app.services.email_service import MockEmailProvider

        with patch("app.services.email_service.settings") as mock_settings:
            mock_settings.EMAIL_PROVIDER = "mock"
            provider = create_email_provider()
        assert isinstance(provider, MockEmailProvider)

    def test_ses_provider_when_configured(self):
        with patch("app.services.email_service.settings") as mock_settings, \
             patch("app.services.email_providers.ses_provider.boto3"):
            mock_settings.EMAIL_PROVIDER = "ses"
            mock_settings.AWS_ACCESS_KEY_ID = "AKIATEST"
            mock_settings.AWS_SECRET_ACCESS_KEY = "SECRET"
            mock_settings.AWS_REGION = "us-east-1"
            provider = create_email_provider()
        assert isinstance(provider, SESEmailProvider)

    def test_ses_provider_requires_credentials(self):
        with patch("app.services.email_service.settings") as mock_settings:
            mock_settings.EMAIL_PROVIDER = "ses"
            mock_settings.AWS_ACCESS_KEY_ID = None
            mock_settings.AWS_SECRET_ACCESS_KEY = None
            with pytest.raises(RuntimeError, match="requires AWS_ACCESS_KEY_ID"):
                create_email_provider()
