"""
Email service — reusable FastAPI service for all outbound email.

SWITCHING TO AWS SES:
1. Set environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, EMAIL_PROVIDER=ses
2. Implement SESEmailProvider in backend/app/services/email_providers/ses_provider.py:
   - Initialize boto3 SES v2 client using the env var credentials
   - Implement send() method using client.send_email()
   - Map SES API response to EmailSendResult
   - Handle SES-specific errors (throttling, invalid address, account suspended)
3. Set up AWS SNS:
   - Create an SNS topic for SES event notifications
   - Configure SES to publish Delivery, Bounce, and Complaint events to the SNS topic
   - Subscribe the webhook endpoint (POST /v1/webhooks/ses-notifications) to the SNS topic
   - Implement SNS signature validation in the webhook endpoint (currently has a TODO)
4. Verify domain in SES console and configure SPF/DKIM/DMARC DNS records
5. Request SES production access (sandbox mode only sends to verified emails)
No changes needed to EmailService, email_log integration, template rendering, or any calling code.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from app.core.config import settings

logger = logging.getLogger(__name__)

# Errors that indicate a transient failure — safe to retry.
_TRANSIENT_ERRORS = {"ServiceUnavailable", "Throttling", "RequestTimeout", "InternalFailure"}

# Max retry attempts (total calls = MAX_RETRIES)
_MAX_RETRIES = 3

# Exponential backoff delays between retries (seconds).
_BACKOFF_DELAYS = [1, 4, 16]

# Minimum delay between bulk sends (seconds).
_BULK_SEND_DELAY = 0.1

# Basic email validation pattern.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class Attachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass
class EmailPayload:
    to_email: str
    subject: str
    html_body: str
    plain_text_body: str
    from_email: str | None = None
    reply_to: str | None = None
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class EmailSendResult:
    message_id: str
    status: str  # "sent", "failed"
    error: str | None = None


# ── Provider protocol ───────────────────────────────────────────────────────


@runtime_checkable
class EmailProvider(Protocol):
    async def send(self, payload: EmailPayload) -> EmailSendResult:
        """Send a single email via the underlying provider."""
        ...


# ── Re-export providers so tests can import from this module ────────────────

from app.services.email_providers.mock_provider import MockEmailProvider  # noqa: E402
from app.services.email_providers.ses_provider import SESEmailProvider  # noqa: E402


# ── Email service ───────────────────────────────────────────────────────────


def _is_transient_error(error: str | None) -> bool:
    """Return True if the error string indicates a transient/retryable failure."""
    if not error:
        return False
    return any(keyword in error for keyword in _TRANSIENT_ERRORS)


class EmailService:
    """
    Core email service with retry logic, rate limiting, and logging.

    Uses a pluggable provider (MockEmailProvider or SESEmailProvider)
    selected via EMAIL_PROVIDER env var. Every send is logged to the
    email_log table via the Supabase admin client.
    """

    def __init__(self, provider: EmailProvider, db_client=None) -> None:
        self._provider = provider
        self._db = db_client
        self._default_from = settings.SES_FROM_EMAIL

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plain_text_body: str,
        from_email: str | None = None,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
        *,
        email_type: str = "general",
        recipient_type: str = "vendor_contact",
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> EmailSendResult:
        """Send a single email. Logs to email_log table."""

        # ── Validate ────────────────────────────────────────────────────
        if not to_email or not _EMAIL_RE.match(to_email):
            raise ValueError(f"Invalid email address: {to_email!r}")

        # ── Build payload ───────────────────────────────────────────────
        payload = EmailPayload(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=plain_text_body,
            from_email=from_email or self._default_from,
            reply_to=reply_to,
            attachments=attachments or [],
        )

        # ── Insert email_log row (status=queued) ────────────────────────
        log_id = self._insert_log(
            recipient_email=to_email,
            recipient_type=recipient_type,
            email_type=email_type,
            subject=subject,
            reference_type=reference_type,
            reference_id=reference_id,
        )

        # ── Send with retry ─────────────────────────────────────────────
        result: EmailSendResult | None = None
        retry_count = 0

        for attempt in range(_MAX_RETRIES):
            result = await self._provider.send(payload)

            if result.status == "sent":
                break

            # Permanent failure — do not retry
            if not _is_transient_error(result.error):
                break

            retry_count = attempt + 1

            # Sleep before next retry (except after last attempt)
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_BACKOFF_DELAYS[attempt])

        assert result is not None  # loop always runs at least once

        # ── Update email_log ────────────────────────────────────────────
        if result.status == "sent":
            self._update_log(log_id, {
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "retry_count": retry_count,
            })
        else:
            self._update_log(log_id, {
                "status": "failed",
                "error_message": result.error,
                "retry_count": retry_count,
            })

        return result

    async def send_bulk_emails(
        self,
        emails: list[EmailPayload],
    ) -> list[EmailSendResult]:
        """Send multiple emails respecting rate limits."""
        results: list[EmailSendResult] = []

        for i, email in enumerate(emails):
            result = await self._provider.send(email)
            results.append(result)

            # Rate-limit delay between sends (skip after last email)
            if i < len(emails) - 1:
                await asyncio.sleep(_BULK_SEND_DELAY)

        return results

    # ── Private helpers ──────────────────────────────────────────────────

    def _insert_log(
        self,
        *,
        recipient_email: str,
        recipient_type: str,
        email_type: str,
        subject: str,
        reference_type: str | None,
        reference_id: str | None,
    ) -> str | None:
        """Insert a queued email_log row. Returns the log row ID."""
        if not self._db:
            return None

        row = {
            "recipient_email": recipient_email,
            "recipient_type": recipient_type,
            "email_type": email_type,
            "subject": subject,
            "reference_type": reference_type,
            "reference_id": reference_id,
            "status": "queued",
        }
        resp = self._db.table("email_log").insert(row).execute()
        return resp.data[0]["id"] if resp.data else None

    def _update_log(self, log_id: str | None, data: dict) -> None:
        """Update an existing email_log row."""
        if not self._db or not log_id:
            return
        self._db.table("email_log").update(data).eq("id", log_id).execute()
