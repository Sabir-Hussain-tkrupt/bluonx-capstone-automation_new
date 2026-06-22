"""
AWS SES email provider — sends real emails via the SES v2 API.

Required environment variables (set in backend/.env):
    AWS_ACCESS_KEY_ID      — IAM access key
    AWS_SECRET_ACCESS_KEY  — IAM secret key
    AWS_REGION             — SES region (default: us-east-1)
    EMAIL_PROVIDER=ses     — activates this provider

In SES sandbox mode, both sender AND recipient must be verified identities.
Request production access in the AWS SES console to remove that restriction.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from app.services.email_service import EmailPayload, EmailSendResult

logger = logging.getLogger(__name__)

# SES errors that are transient — the EmailService retry logic will retry these.
_TRANSIENT_ERROR_CODES = {"Throttling", "TooManyRequestsException", "ServiceUnavailable"}

# SES errors that are permanent — no point retrying.
_PERMANENT_ERROR_CODES = {
    "MessageRejected",
    "AccountSendingPausedException",
    "MailFromDomainNotVerifiedException",
    "ConfigurationSetDoesNotExistException",
}


class SESEmailProvider:
    """AWS SES v2 email provider."""

    def __init__(
        self,
        *,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        configuration_set: str | None = None,
    ) -> None:
        self._client = boto3.client(
            "sesv2",
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )
        self._configuration_set = configuration_set
        logger.info(
            "SES email provider initialised (region=%s, configuration_set=%s)",
            region,
            configuration_set or "<none>",
        )

    async def send(self, payload: "EmailPayload") -> "EmailSendResult":
        from app.services.email_service import EmailSendResult

        destination = {"ToAddresses": [payload.to_email]}

        # Build email content — multipart/alternative (HTML + plain text)
        content: dict = {
            "Simple": {
                "Subject": {"Data": payload.subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": payload.plain_text_body, "Charset": "UTF-8"},
                    "Html": {"Data": payload.html_body, "Charset": "UTF-8"},
                },
            }
        }

        kwargs: dict = {
            "FromEmailAddress": payload.from_email,
            "Destination": destination,
            "Content": content,
        }

        if payload.reply_to:
            kwargs["ReplyToAddresses"] = [payload.reply_to]

        # Tag the send with a configuration set so SES publishes
        # Delivery/Bounce/Complaint events to SNS. Omitted when unset.
        if self._configuration_set:
            kwargs["ConfigurationSetName"] = self._configuration_set

        try:
            response = self._client.send_email(**kwargs)
            message_id = response.get("MessageId", "")
            logger.info(
                "SES email sent: to=%s message_id=%s",
                payload.to_email,
                message_id,
            )
            return EmailSendResult(
                message_id=message_id,
                status="sent",
                error=None,
            )

        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            error_message = exc.response.get("Error", {}).get("Message", str(exc))

            # Classify error for the retry logic in EmailService.
            # Transient errors → EmailService will retry (up to 3 times).
            # Permanent errors → EmailService will NOT retry.
            if error_code in _TRANSIENT_ERROR_CODES:
                logger.warning(
                    "SES transient error (will retry): %s — %s",
                    error_code,
                    error_message,
                )
                return EmailSendResult(
                    message_id="",
                    status="failed",
                    error=error_code,
                )

            # Permanent failure — log as error, no retry.
            logger.error(
                "SES permanent error: %s — %s",
                error_code,
                error_message,
            )
            return EmailSendResult(
                message_id="",
                status="failed",
                error=f"{error_code}: {error_message}",
            )

        except Exception as exc:
            # Unexpected error — treat as transient so retry logic kicks in.
            logger.exception("Unexpected SES error")
            return EmailSendResult(
                message_id="",
                status="failed",
                error=f"ServiceUnavailable: {exc}",
            )
