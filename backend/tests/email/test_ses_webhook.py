"""
Tests for the SNS webhook endpoint: POST /api/v1/webhooks/ses-notifications.

Verifies that SES delivery/bounce/complaint events update email_log rows,
SNS subscription confirmations are auto-confirmed, and invalid signatures
are rejected.
"""

import base64
import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app.main import app
from app.routers.webhooks import _build_signing_string, verify_sns_signature


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
def delivery_event_configset() -> dict:
    """Delivery in the CONFIGURATION SET event-publishing shape (eventType),
    as opposed to the legacy identity-notification shape (notificationType)."""
    ses_message = {
        "eventType": "Delivery",
        "mail": {
            "timestamp": "2026-06-22T12:00:00.000Z",
            "messageId": "ses-msg-configset-evt-001",
            "source": "noreply@bluonx.com",
            "destination": ["vendor@example.com"],
        },
        "delivery": {
            "timestamp": "2026-06-22T12:00:01.000Z",
            "recipients": ["vendor@example.com"],
            "smtpResponse": "250 2.0.0 OK",
        },
    }
    return {
        "Type": "Notification",
        "MessageId": "ee85e39f-ea4d-435a-b922-c6aae3915eff",
        "TopicArn": "arn:aws:sns:us-east-1:314727362874:bluonx-ses-events-dev",
        "Subject": "Amazon SES Email Event Notification",
        "Message": json.dumps(ses_message),
        "Timestamp": "2026-06-22T12:00:02.000Z",
        "SignatureVersion": "1",
        "Signature": "EXAMPLE_SIGNATURE_BASE64==",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-abc123.pem",
        "UnsubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=Unsubscribe",
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
        # Must join on the provider message id, NOT the internal UUID PK.
        assert update_chain.eq.call_args[0] == (
            "provider_message_id",
            "ses-msg-delivery-001",
        )

    def test_configset_eventtype_updates_status(self, test_client, delivery_event_configset):
        """Configuration-set events use 'eventType' (not 'notificationType').
        The handler must accept that shape and still mark the row delivered."""
        with patch("app.routers.webhooks.verify_sns_signature", return_value=True), \
             patch("app.routers.webhooks.get_supabase") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            update_chain = MagicMock()
            update_chain.eq.return_value.execute.return_value = MagicMock(data=[{"id": "x"}])
            mock_db.table.return_value.update.return_value = update_chain

            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=delivery_event_configset,
                headers={"x-amz-sns-message-type": "Notification"},
            )

        assert resp.status_code == 200
        update_call = mock_db.table("email_log").update.call_args[0][0]
        assert update_call["status"] == "delivered"
        assert update_chain.eq.call_args[0] == (
            "provider_message_id",
            "ses-msg-configset-evt-001",
        )

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
        # Must join on the provider message id, NOT the internal UUID PK.
        assert update_chain.eq.call_args[0] == (
            "provider_message_id",
            "ses-msg-bounce-002",
        )

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
        update_call = mock_db.table("email_log").update.call_args[0][0]
        assert update_call["status"] == "failed"
        # Must join on the provider message id, NOT the internal UUID PK.
        assert update_chain.eq.call_args[0] == (
            "provider_message_id",
            "ses-msg-complaint-003",
        )


# ── Signature canonical string (real, not mocked) ───────────────────────────


class TestSigningString:
    """The string-to-sign must follow the AWS field order for each type.

    These exercise the real signing logic that the patched-verifier tests skip.
    The SubscriptionConfirmation canonical string must include Token between
    Timestamp and TopicArn, or the genuine confirmation is rejected with 403.
    """

    def test_confirmation_signing_string_includes_token(self):
        payload = {
            "Type": "SubscriptionConfirmation",
            "Message": "m",
            "MessageId": "id-1",
            "SubscribeURL": "https://sns.example/confirm",
            "Timestamp": "2026-06-21T00:00:00.000Z",
            "Token": "tok-123",
            "TopicArn": "arn:aws:sns:us-east-1:1:t",
        }
        expected = (
            "Message\nm\n"
            "MessageId\nid-1\n"
            "SubscribeURL\nhttps://sns.example/confirm\n"
            "Timestamp\n2026-06-21T00:00:00.000Z\n"
            "Token\ntok-123\n"
            "TopicArn\narn:aws:sns:us-east-1:1:t\n"
            "Type\nSubscriptionConfirmation\n"
        )
        assert _build_signing_string(payload) == expected

    def test_notification_signing_string_has_no_token(self):
        payload = {
            "Type": "Notification",
            "Message": "m",
            "MessageId": "id-1",
            "Subject": "s",
            "Timestamp": "2026-06-21T00:00:00.000Z",
            "TopicArn": "arn:aws:sns:us-east-1:1:t",
        }
        assert "Token" not in _build_signing_string(payload)


class TestVerifyConfirmationSignatureRoundTrip:
    """Full RSA sign-then-verify of a SubscriptionConfirmation. This is the path
    the genuine SNS confirmation takes, which the patched-verifier tests bypass.
    """

    @staticmethod
    def _self_signed_cert(key: rsa.RSAPrivateKey) -> bytes:
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256())
        )
        return cert.public_bytes(serialization.Encoding.PEM)

    def _signed_payload(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        payload = {
            "Type": "SubscriptionConfirmation",
            "Message": "You have chosen to subscribe.",
            "MessageId": "abc-123",
            "SubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=ConfirmSubscription&Token=xyz",
            "Timestamp": "2026-06-21T00:00:00.000Z",
            "Token": "xyz",
            "TopicArn": "arn:aws:sns:us-east-1:314727362874:bluonx-ses-events-dev",
            "SignatureVersion": "1",
            "SigningCertURL": "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-abc.pem",
        }
        signing_string = _build_signing_string(payload)
        sig = key.sign(signing_string.encode("utf-8"), padding.PKCS1v15(), hashes.SHA1())
        payload["Signature"] = base64.b64encode(sig).decode()
        return payload, self._self_signed_cert(key)

    def test_valid_confirmation_signature_passes(self):
        payload, cert_pem = self._signed_payload()
        with patch("app.routers.webhooks.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(content=cert_pem, raise_for_status=lambda: None)
            assert verify_sns_signature(payload) is True

    def test_tampered_token_fails_verification(self):
        payload, cert_pem = self._signed_payload()
        payload["Token"] = "tampered"  # signature no longer matches
        with patch("app.routers.webhooks.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(content=cert_pem, raise_for_status=lambda: None)
            assert verify_sns_signature(payload) is False


# ── Correlation-key hardening ───────────────────────────────────────────────


class TestMessageIdHardening:
    """Guards around the provider_message_id correlation key."""

    def test_missing_message_id_skips_update(self, test_client, delivery_notification):
        """A notification with an empty mail.messageId must not attempt an
        email_log update (an empty key must never match rows)."""
        ses_message = json.loads(delivery_notification["Message"])
        ses_message["mail"]["messageId"] = ""
        delivery_notification["Message"] = json.dumps(ses_message)

        with patch("app.routers.webhooks.verify_sns_signature", return_value=True), \
             patch("app.routers.webhooks.get_supabase") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            resp = test_client.post(
                "/api/v1/webhooks/ses-notifications",
                json=delivery_notification,
                headers={"x-amz-sns-message-type": "Notification"},
            )

        assert resp.status_code == 200
        mock_db.table.return_value.update.assert_not_called()

    def test_zero_row_match_still_200_and_warns(
        self, test_client, bounce_notification, caplog
    ):
        """When no email_log row matches the MessageId, the endpoint still
        returns 200 but logs a warning (no silent no-op)."""
        import logging

        with patch("app.routers.webhooks.verify_sns_signature", return_value=True), \
             patch("app.routers.webhooks.get_supabase") as mock_get_db, \
             caplog.at_level(logging.WARNING, logger="app.routers.webhooks"):
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
        assert any(
            "no email_log row matched" in rec.message for rec in caplog.records
        )


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
