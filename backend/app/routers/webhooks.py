"""
Webhook endpoints — stubs only (Task 4.3 test-first).

Handles inbound notifications from external services (AWS SNS for SES events).
"""

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.post("/webhooks/ses-notifications")
async def ses_notifications(request: Request) -> Response:
    """
    Receive AWS SNS notifications for SES delivery/bounce/complaint events.

    Public endpoint (no auth) — validates SNS message signature instead.
    Handles:
      - SubscriptionConfirmation: auto-confirms the SNS subscription
      - Notification: processes Delivery/Bounce/Complaint events
    """
    raise NotImplementedError("SES webhook handler not implemented yet")
