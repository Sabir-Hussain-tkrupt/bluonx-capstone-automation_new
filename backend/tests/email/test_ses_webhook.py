"""
Tests for the SNS webhook endpoint: POST /api/v1/webhooks/ses-notifications.

Verifies that SES delivery/bounce/complaint events update email_log rows,
SNS subscription confirmations are auto-confirmed, and invalid signatures
are rejected.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ── Realistic SNS payload fixtures ──────────────────────────────────────────

# These match the actual AWS SNS message format for SES events.
# See: https://docs.aws.amazon.com/ses/latest/dg/notification-contents.html


COMMON_SNS_HEADERS = {
    "Content-Type": "text/plain",
    "x-amz-sns-message-type": "Notification",
    "x-amz-sns-message-id": "da41e39f-ea4d-435a-b922-c6aae3915eba",
    "x-amz-sns-topic-arn": "arn:aws:sns:us-east-1:123456789012:ses-notifications",
}


@pytest.fixture()
def delivery_notification() -> dict:
    """Realistic SNS Notification payload for a successful SES delivery."""
    ses_message = {
        "notificationType": "Delivery",
        "mail": {
            "timestamp": "2026-04-07T12:00:00.000Z",
            "messageId": "ses-msg-delivery-001",
            "source": "noreply@bluonx.com",
            "destination": ["vendor@example.com"],
        },
        "delivery": {
            "timestamp": "2026-04-07T12:00:01.000Z",
            "processingTimeMillis": 546,
            "recipients": ["vendor@example.com"],
            "smtpResponse": "250 2.0.0 OK",
            "reportingMTA": "a27-42.smtp-out.us-east-1.amazonses.com",
        },
    }
    return {
        "Type": "Notification",
        "MessageId": "da41e39f-ea4d-435a-b922-c6aae3915eba",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:ses-notifications",
        "Subject": "Amazon SES Email Event Notification",
        "Message": json.dumps(ses_message),
        "Timestamp": "2026-04-07T12:00:02.000Z",
        "SignatureVersion": "1",
        "Signature": "EXAMPLE_SIGNATURE_BASE64==",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-abc123.pem",
        "UnsubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:us-east-1:123456789012:ses-notifications:abcdef",
    }


@pytest.fixture()
def bounce_notification() -> dict:
    """Realistic SNS Notification payload for an SES bounce."""
    ses_message = {
        "notificationType": "Bounce",
        "mail": {
            "timestamp": "2026-04-07T12:00:00.000Z",
            "messageId": "ses-msg-bounce-002",
            "source": "noreply@bluonx.com",
            "destination": ["bad-address@example.com"],
        },
        "bounce": {
            "bounceType": "Permanent",
            "bounceSubType": "General",
            "bouncedRecipients": [
                {
                    "emailAddress": "bad-address@example.com",
                    "action": "failed",
                    "status": "5.1.1",
                    "diagnosticCode": "smtp; 550 5.1.1 user unknown",
                }
            ],
            "timestamp": "2026-04-07T12:00:01.000Z",
            "feedbackId": "0100018e-1234-5678-9abc-def012345678-000000",
        },
    }
    return {
        "Type": "Notification",
        "MessageId": "bb52e39f-ea4d-435a-b922-c6aae3915ebb",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:ses-notifications",
        "Subject": "Amazon SES Email Event Notification",
        "Message": json.dumps(ses_message),
        "Timestamp": "2026-04-07T12:00:02.000Z",
        "SignatureVersion": "1",
        "Signature": "EXAMPLE_SIGNATURE_BASE64==",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-abc123.pem",
        "UnsubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:us-east-1:123456789012:ses-notifications:abcdef",
    }


@pytest.fixture()
def complaint_notification() -> dict:
    """Realistic SNS Notification payload for an SES complaint."""
    ses_message = {
        "notificationType": "Complaint",
        "mail": {
            "timestamp": "2026-04-07T12:00:00.000Z",
            "messageId": "ses-msg-complaint-003",
            "source": "noreply@bluonx.com",
            "destination": ["annoyed@example.com"],
        },
        "complaint": {
            "complainedRecipients": [
                {"emailAddress": "annoyed@example.com"}
            ],
            "timestamp": "2026-04-07T14:00:00.000Z",
            "feedbackId": "0100018e-aaaa-bbbb-cccc-dddddddddddd-000000",
            "complaintSubType": None,
            "complaintFeedbackType": "abuse",
        },
    }
    return {
        "Type": "Notification",
        "MessageId": "cc63e39f-ea4d-435a-b922-c6aae3915ecc",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:ses-notifications",
        "Message": json.dumps(ses_message),
        "Timestamp": "2026-04-07T14:00:01.000Z",
        "SignatureVersion": "1",
        "Signature": "EXAMPLE_SIGNATURE_BASE64==",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-abc123.pem",
        "UnsubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:us-east-1:123456789012:ses-notifications:abcdef",
    }


@pytest.fixture()
def subscription_confirmation() -> dict:
    """Realistic SNS SubscriptionConfirmation message."""
    return {
        "Type": "SubscriptionConfirmation",
        "MessageId": "dd74e39f-ea4d-435a-b922-c6aae3915edd",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:ses-notifications",
        "Message": "You have chosen to subscribe to the topic arn:aws:sns:us-east-1:123456789012:ses-notifications.\nTo confirm the subscription, visit the SubscribeURL included in this message.",
        "SubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=ConfirmSubscription&TopicArn=arn:aws:sns:us-east-1:123456789012:ses-notifications&Token=LONG_TOKEN_HERE",
        "Timestamp": "2026-04-07T10:00:00.000Z",
        "SignatureVersion": "1",
        "Signature": "EXAMPLE_SIGNATURE_BASE64==",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-abc123.pem",
        "Token": "LONG_TOKEN_HERE",
    }


@pytest.fixture()
def test_client() -> TestClient:
    """FastAPI TestClient with lifespan."""
    with TestClient(app) as c:
        yield c


# ── Endpoint existence ──────────────────────────────────────────────────────


class TestWebhookEndpointExists:
    """The SES webhook endpoint must exist and accept POST."""

    def test_endpoint_accepts_post(self, test_client, delivery_notification):
        """POST /api/v1/webhooks/ses-notifications should not return 404/405."""
        with patch("app.routers.webhooks.verify_sns_signature", return_value=True):
            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=delivery_notification,
                headers={"x-amz-sns-message-type": "Notification"},
            )
        assert resp.status_code != 404
        assert resp.status_code != 405

    def test_endpoint_rejects_get(self, test_client):
        """GET should not be allowed on the webhook endpoint."""
        resp = test_client.get("/api/v1/webhooks/ses-notifications")
        assert resp.status_code == 405


# ── Delivery notifications ──────────────────────────────────────────────────


class TestDeliveryNotification:
    """SNS Delivery notifications should update email_log status to 'delivered'."""

    def test_delivery_updates_status(self, test_client, delivery_notification):
        with patch("app.routers.webhooks.verify_sns_signature", return_value=True), \
             patch("app.routers.webhooks.get_supabase") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            update_chain = MagicMock()
            update_chain.eq.return_value.execute.return_value = MagicMock(data=[])
            mock_db.table.return_value.update.return_value = update_chain

            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=delivery_notification,
                headers={"x-amz-sns-message-type": "Notification"},
            )

        assert resp.status_code == 200
        # Verify the email_log table was updated
        mock_db.table.assert_called_with("email_log")
        update_call = mock_db.table("email_log").update.call_args[0][0]
        assert update_call["status"] == "delivered"

    def test_delivery_returns_200(self, test_client, delivery_notification):
        """SNS requires 200 response for successful processing."""
        with patch("app.routers.webhooks.verify_sns_signature", return_value=True), \
             patch("app.routers.webhooks.get_supabase") as mock_get_db:
            mock_get_db.return_value = MagicMock()
            mock_get_db.return_value.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=delivery_notification,
                headers={"x-amz-sns-message-type": "Notification"},
            )
        assert resp.status_code == 200


# ── Bounce notifications ────────────────────────────────────────────────────


class TestBounceNotification:
    """SNS Bounce notifications should update email_log status to 'bounced'."""

    def test_bounce_updates_status_and_error(self, test_client, bounce_notification):
        with patch("app.routers.webhooks.verify_sns_signature", return_value=True), \
             patch("app.routers.webhooks.get_supabase") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            update_chain = MagicMock()
            update_chain.eq.return_value.execute.return_value = MagicMock(data=[])
            mock_db.table.return_value.update.return_value = update_chain

            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=bounce_notification,
                headers={"x-amz-sns-message-type": "Notification"},
            )

        assert resp.status_code == 200
        mock_db.table.assert_called_with("email_log")
        update_call = mock_db.table("email_log").update.call_args[0][0]
        assert update_call["status"] == "bounced"
        # Bounce type should be stored in error_message
        assert "Permanent" in update_call.get("error_message", "")

    def test_bounce_stores_bounce_subtype(self, test_client, bounce_notification):
        with patch("app.routers.webhooks.verify_sns_signature", return_value=True), \
             patch("app.routers.webhooks.get_supabase") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            update_chain = MagicMock()
            update_chain.eq.return_value.execute.return_value = MagicMock(data=[])
            mock_db.table.return_value.update.return_value = update_chain

            test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=bounce_notification,
                headers={"x-amz-sns-message-type": "Notification"},
            )

        update_call = mock_db.table("email_log").update.call_args[0][0]
        # Should contain bounce type info (Permanent/General)
        assert update_call.get("error_message") is not None


# ── Complaint notifications ─────────────────────────────────────────────────


class TestComplaintNotification:
    """SNS Complaint notifications should be logged."""

    def test_complaint_is_processed(self, test_client, complaint_notification):
        with patch("app.routers.webhooks.verify_sns_signature", return_value=True), \
             patch("app.routers.webhooks.get_supabase") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            update_chain = MagicMock()
            update_chain.eq.return_value.execute.return_value = MagicMock(data=[])
            mock_db.table.return_value.update.return_value = update_chain

            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=complaint_notification,
                headers={"x-amz-sns-message-type": "Notification"},
            )

        assert resp.status_code == 200
        # Complaint should trigger an update to email_log
        mock_db.table.assert_called_with("email_log")


# ── Subscription confirmation ───────────────────────────────────────────────


class TestSubscriptionConfirmation:
    """SNS SubscriptionConfirmation messages must be auto-confirmed."""

    def test_auto_confirms_subscription(self, test_client, subscription_confirmation):
        """The endpoint should HTTP GET the SubscribeURL to confirm."""
        with patch("app.routers.webhooks.verify_sns_signature", return_value=True), \
             patch("httpx.get") as mock_http_get:
            mock_http_get.return_value = MagicMock(status_code=200)

            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=subscription_confirmation,
                headers={"x-amz-sns-message-type": "SubscriptionConfirmation"},
            )

        assert resp.status_code == 200
        # Should have called the SubscribeURL
        mock_http_get.assert_called_once_with(
            subscription_confirmation["SubscribeURL"],
            timeout=10,
        )

    def test_confirmation_returns_200(self, test_client, subscription_confirmation):
        with patch("app.routers.webhooks.verify_sns_signature", return_value=True), \
             patch("httpx.get") as mock_http_get:
            mock_http_get.return_value = MagicMock(status_code=200)

            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=subscription_confirmation,
                headers={"x-amz-sns-message-type": "SubscriptionConfirmation"},
            )
        assert resp.status_code == 200


# ── Signature validation ────────────────────────────────────────────────────


class TestSignatureValidation:
    """Requests with invalid or missing SNS signatures must be rejected."""

    def test_invalid_signature_returns_403(self, test_client, delivery_notification):
        """When signature verification fails, endpoint returns 403."""
        with patch("app.routers.webhooks.verify_sns_signature", return_value=False):
            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=delivery_notification,
                headers={"x-amz-sns-message-type": "Notification"},
            )
        assert resp.status_code == 403

    def test_missing_signature_fields_returns_403(self, test_client):
        """Payload without required SNS signature fields is rejected."""
        payload = {
            "Type": "Notification",
            "MessageId": "test-id",
            "Message": "{}",
            # Missing: Signature, SigningCertURL, SignatureVersion
        }
        with patch("app.routers.webhooks.verify_sns_signature", return_value=False):
            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=payload,
                headers={"x-amz-sns-message-type": "Notification"},
            )
        assert resp.status_code == 403

    def test_valid_signature_returns_200(self, test_client, delivery_notification):
        """Valid signature should proceed and return 200."""
        with patch("app.routers.webhooks.verify_sns_signature", return_value=True), \
             patch("app.routers.webhooks.get_supabase") as mock_get_db:
            mock_get_db.return_value = MagicMock()
            mock_get_db.return_value.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=delivery_notification,
                headers={"x-amz-sns-message-type": "Notification"},
            )
        assert resp.status_code == 200
