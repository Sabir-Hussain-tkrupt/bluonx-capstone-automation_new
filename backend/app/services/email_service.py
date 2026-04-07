"""
Email service — stubs only (Task 4.3 test-first).

These types and classes define the contract that the implementation must satisfy.
All methods raise NotImplementedError until the real implementation is built.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


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


# ── Mock provider stub ──────────────────────────────────────────────────────


class MockEmailProvider:
    """Console-logging email provider for development/testing."""

    async def send(self, payload: EmailPayload) -> EmailSendResult:
        raise NotImplementedError("MockEmailProvider.send not implemented yet")


# ── SES provider stub ───────────────────────────────────────────────────────


class SESEmailProvider:
    """AWS SES email provider."""

    async def send(self, payload: EmailPayload) -> EmailSendResult:
        raise NotImplementedError("SESEmailProvider.send not implemented yet")


# ── Email service stub ──────────────────────────────────────────────────────


class EmailService:
    """
    Core email service with retry logic, rate limiting, and logging.

    Uses a pluggable provider (MockEmailProvider or SESEmailProvider)
    selected via EMAIL_PROVIDER env var.
    """

    def __init__(self, provider: EmailProvider, db_client=None) -> None:
        raise NotImplementedError("EmailService.__init__ not implemented yet")

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
        raise NotImplementedError("EmailService.send_email not implemented yet")

    async def send_bulk_emails(
        self,
        emails: list[EmailPayload],
    ) -> list[EmailSendResult]:
        """Send multiple emails respecting rate limits."""
        raise NotImplementedError("EmailService.send_bulk_emails not implemented yet")
