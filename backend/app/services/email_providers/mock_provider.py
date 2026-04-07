"""
Mock email provider — logs emails to console instead of sending.

Used when EMAIL_PROVIDER=mock (default). Produces the same EmailSendResult
interface as the real SES provider so calling code is identical.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from app.services.email_service import EmailSendResult

logger = logging.getLogger(__name__)


class MockEmailProvider:
    """Console-logging email provider for development and testing."""

    async def send(self, payload) -> "EmailSendResult":
        from app.services.email_service import EmailSendResult

        message_id = f"mock-{uuid4()}"

        logger.info(
            "[MOCK EMAIL] To: %s | From: %s | Subject: %s | Body preview: %.80s",
            payload.to_email,
            payload.from_email,
            payload.subject,
            payload.plain_text_body,
        )

        return EmailSendResult(
            message_id=message_id,
            status="sent",
            error=None,
        )
