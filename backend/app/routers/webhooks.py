"""
Webhook endpoints for inbound notifications from external services.

Handles AWS SNS notifications for SES delivery/bounce/complaint events.
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, Request, Response, status

from app.core.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()


# ── SNS signature verification ──────────────────────────────────────────────


def verify_sns_signature(payload: dict) -> bool:
    """
    Verify the cryptographic signature of an incoming SNS message.

    TODO: Implement real SNS signature verification when AWS credentials arrive.
    Steps:
      1. Download the signing certificate from payload["SigningCertURL"]
      2. Verify the URL is from amazonaws.com (prevent spoofing)
      3. Build the canonical message string for the message type
      4. Verify the signature using the certificate's public key
    See: https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html

    For now, returns True to allow development/testing to proceed.
    """
    return True


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
            notification_type = message.get("notificationType", "")
            ses_message_id = message.get("mail", {}).get("messageId", "")

            db = get_supabase(request)

            if notification_type == "Delivery":
                logger.info("SES delivery confirmed for message %s", ses_message_id)
                db.table("email_log").update({
                    "status": "delivered",
                }).eq("id", ses_message_id).execute()

            elif notification_type == "Bounce":
                bounce = message.get("bounce", {})
                bounce_type = bounce.get("bounceType", "Unknown")
                bounce_sub_type = bounce.get("bounceSubType", "Unknown")
                error_msg = f"{bounce_type}/{bounce_sub_type}"
                logger.warning(
                    "SES bounce for message %s: %s", ses_message_id, error_msg,
                )
                db.table("email_log").update({
                    "status": "bounced",
                    "error_message": error_msg,
                }).eq("id", ses_message_id).execute()

            elif notification_type == "Complaint":
                complaint = message.get("complaint", {})
                feedback_type = complaint.get("complaintFeedbackType", "unknown")
                logger.warning(
                    "SES complaint for message %s: %s", ses_message_id, feedback_type,
                )
                db.table("email_log").update({
                    "status": "failed",
                    "error_message": f"Complaint: {feedback_type}",
                }).eq("id", ses_message_id).execute()

            else:
                logger.info("Unhandled SNS notification type: %s", notification_type)

        except Exception:
            # Always return 200 — SNS retries on non-2xx and we don't want
            # a DB error to cause infinite retry loops from AWS.
            logger.exception("Error processing SNS notification")

    return Response(status_code=200, content="OK")
