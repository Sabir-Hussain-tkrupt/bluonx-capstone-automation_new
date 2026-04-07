"""
AWS SES email provider — placeholder for when AWS credentials arrive.

SWITCHING TO AWS SES:
1. Set environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, EMAIL_PROVIDER=ses
2. Implement this class:
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


class SESEmailProvider:
    """AWS SES email provider (not implemented — requires AWS credentials)."""

    async def send(self, payload) -> "EmailSendResult":
        from app.services.email_service import EmailSendResult  # noqa: F811

        raise NotImplementedError(
            "SESEmailProvider requires AWS credentials. "
            "Set EMAIL_PROVIDER=mock for development or configure "
            "AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION."
        )
