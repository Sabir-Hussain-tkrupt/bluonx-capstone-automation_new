"""
Webhook endpoints for inbound notifications from external services.

Handles AWS SNS notifications for SES delivery/bounce/complaint events.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from urllib.parse import urlparse

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, utils
from fastapi import APIRouter, Request, Response, status

from app.core.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()

# Cert URL must be from amazonaws.com on HTTPS to prevent spoofing.
_VALID_CERT_URL_RE = re.compile(
    r"^https://sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?/"
)


# ── SNS signature verification ──────────────────────────────────────────────


def _build_signing_string(payload: dict) -> str:
    """
    Build the canonical string-to-sign for an SNS message.

    The fields and order differ by message type.
    See: https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html
    """
    msg_type = payload.get("Type", "")

    if msg_type == "Notification":
        fields = ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
    else:
        # SubscriptionConfirmation and UnsubscribeConfirmation. These include
        # the Token field in the canonical string-to-sign (between Timestamp and
        # TopicArn); omitting it makes the signature never match, so the genuine
        # confirmation is rejected and the subscription stays pending.
        fields = ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]

    parts: list[str] = []
    for field in fields:
        value = payload.get(field)
        if value is not None:
            parts.append(field)
            parts.append(str(value))

    return "\n".join(parts) + "\n"


def verify_sns_signature(payload: dict) -> bool:
    """
    Verify the cryptographic signature of an incoming SNS message.

    Steps:
      1. Validate SigningCertURL is from amazonaws.com (HTTPS)
      2. Download the X.509 certificate
      3. Build the canonical signing string
      4. Verify the signature using the certificate's public key (SHA1WithRSA)

    Returns True if the signature is valid, False otherwise.
    """
    cert_url = payload.get("SigningCertURL", "")
    signature_b64 = payload.get("Signature", "")
    sig_version = payload.get("SignatureVersion", "")

    # ── Basic field validation ──────────────────────────────────────
    if not cert_url or not signature_b64:
        logger.warning("SNS message missing SigningCertURL or Signature")
        return False

    # Only SignatureVersion "1" is supported (SHA1WithRSA).
    if sig_version not in ("1", "2"):
        logger.warning("Unsupported SNS SignatureVersion: %s", sig_version)
        return False

    # ── Validate cert URL origin ────────────────────────────────────
    if not _VALID_CERT_URL_RE.match(cert_url):
        logger.warning("SNS SigningCertURL not from amazonaws.com: %s", cert_url)
        return False

    parsed = urlparse(cert_url)
    if parsed.scheme != "https":
        logger.warning("SNS SigningCertURL is not HTTPS: %s", cert_url)
        return False

    try:
        # ── Download certificate ────────────────────────────────────
        cert_resp = httpx.get(cert_url, timeout=10)
        cert_resp.raise_for_status()
        cert = x509.load_pem_x509_certificate(cert_resp.content)

        # ── Build signing string and verify ─────────────────────────
        signing_string = _build_signing_string(payload)
        signature = base64.b64decode(signature_b64)

        hash_algo = hashes.SHA256() if sig_version == "2" else hashes.SHA1()

        cert.public_key().verify(
            signature,
            signing_string.encode("utf-8"),
            padding.PKCS1v15(),
            hash_algo,
        )

        return True

    except Exception:
        logger.exception("SNS signature verification failed")
        return False


# ── SES notification webhook ────────────────────────────────────────────────


@router.post("/webhooks/ses-notifications")
async def ses_notifications(request: Request) -> Response:
    """
    Receive AWS SNS notifications for SES delivery/bounce/complaint events.

    Public endpoint (no JWT auth) — validates SNS message signature instead.
    Always returns 200 (SNS retries on non-2xx responses).
    """
    body = await request.json()

    # ── Validate signature ──────────────────────────────────────────
    if not verify_sns_signature(body):
        return Response(status_code=status.HTTP_403_FORBIDDEN, content="Invalid SNS signature")

    msg_type = body.get("Type", "")

    # ── Subscription confirmation ───────────────────────────────────
    if msg_type == "SubscriptionConfirmation":
        subscribe_url = body.get("SubscribeURL")
        if subscribe_url:
            logger.info("Confirming SNS subscription: %s", subscribe_url)
            httpx.get(subscribe_url, timeout=10)
        return Response(status_code=200, content="OK")

    # ── Notification ────────────────────────────────────────────────
    if msg_type == "Notification":
        try:
            message_str = body.get("Message", "{}")
            message = json.loads(message_str)
            # SES emits two shapes: configuration-set event publishing uses
            # "eventType"; legacy identity feedback notifications use
            # "notificationType". The branch values are identical, so accept
            # either. We use a configuration set, so eventType is the live path.
            notification_type = message.get("eventType") or message.get("notificationType", "")
            ses_message_id = message.get("mail", {}).get("messageId", "")
            logger.info(
                "SNS event received: type=%s messageId=%s",
                notification_type or "<empty>",
                ses_message_id or "<empty>",
            )

            # The SES MessageId is the only key shared between the send path
            # and this async callback. An empty value must never be used to
            # match rows (it would match nothing useful and risks NULLs).
            if not ses_message_id:
                logger.warning(
                    "SNS %s notification missing mail.messageId, skipping update",
                    notification_type,
                )
                return Response(status_code=200, content="OK")

            db = get_supabase(request)

            def _update_email_log(fields: dict) -> None:
                """Update the email_log row matched by provider_message_id.

                Logs when no row matched so a missing/mismatched correlation
                surfaces instead of silently updating nothing.
                """
                resp = (
                    db.table("email_log")
                    .update(fields)
                    .eq("provider_message_id", ses_message_id)
                    .execute()
                )
                if not resp.data:
                    logger.warning(
                        "SNS %s: no email_log row matched provider_message_id %s",
                        notification_type,
                        ses_message_id,
                    )

            if notification_type == "Delivery":
                logger.info("SES delivery confirmed for message %s", ses_message_id)
                _update_email_log({"status": "delivered"})

            elif notification_type == "Bounce":
                bounce = message.get("bounce", {})
                bounce_type = bounce.get("bounceType", "Unknown")
                bounce_sub_type = bounce.get("bounceSubType", "Unknown")
                error_msg = f"{bounce_type}/{bounce_sub_type}"
                logger.warning(
                    "SES bounce for message %s: %s", ses_message_id, error_msg,
                )
                _update_email_log({"status": "bounced", "error_message": error_msg})

            elif notification_type == "Complaint":
                complaint = message.get("complaint", {})
                feedback_type = complaint.get("complaintFeedbackType", "unknown")
                logger.warning(
                    "SES complaint for message %s: %s", ses_message_id, feedback_type,
                )
                _update_email_log({
                    "status": "failed",
                    "error_message": f"Complaint: {feedback_type}",
                })

            else:
                logger.info("Unhandled SNS notification type: %s", notification_type)

        except Exception:
            # Always return 200 — SNS retries on non-2xx and we don't want
            # a DB error to cause infinite retry loops from AWS.
            logger.exception("Error processing SNS notification")

    return Response(status_code=200, content="OK")
