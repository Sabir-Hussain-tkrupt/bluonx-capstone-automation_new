"""
AWS SES Integration Test — run manually after configuring credentials.

This script sends a real email through AWS SES to verify that:
  1. AWS credentials (access key, secret key, region) are valid
  2. The "from" email/domain is verified in SES
  3. The "to" email is verified (required in SES sandbox mode)
  4. The full EmailService pipeline works end-to-end

Usage:
    cd backend
    python -m tests.test_ses_integration \
        --to your-email@example.com \
        --from noreply@yourdomain.com \
        --region us-east-1

Prerequisites:
    1. pip install boto3
    2. Set environment variables (or add to backend/.env):
         AWS_ACCESS_KEY_ID=AKIA...
         AWS_SECRET_ACCESS_KEY=...
         AWS_REGION=us-east-1          (or your SES region)
         SES_FROM_EMAIL=noreply@yourdomain.com
    3. In SES sandbox mode, BOTH sender and recipient must be verified:
         - Verify sender domain or email in AWS SES console
         - Verify recipient email in AWS SES console
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load backend/.env so boto3 picks up AWS credentials automatically
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("ses-integration-test")


# ─── Direct boto3 credential check (no app dependencies) ────────────────────


def check_credentials(region: str) -> bool:
    """Verify AWS credentials can authenticate with SES."""
    try:
        import boto3
    except ImportError:
        logger.error("boto3 is not installed. Run: pip install boto3")
        return False

    try:
        client = boto3.client("sesv2", region_name=region)
        account = client.get_account()
        send_quota = account.get("SendQuota", {})
        logger.info("AWS SES account verified!")
        logger.info(
            "  Send quota: %.0f/day | Max send rate: %.0f/sec",
            send_quota.get("Max24HourSend", 0),
            send_quota.get("MaxSendRate", 0),
        )
        production = account.get("ProductionAccessEnabled", False)
        if production:
            logger.info("  Access: PRODUCTION (can send to any address)")
        else:
            logger.warning("  Access: SANDBOX (can only send to verified addresses)")
        return True
    except Exception as e:
        logger.error("AWS credential check failed: %s", e)
        return False


def check_sender_identity(from_email: str, region: str) -> bool:
    """Verify the sender email/domain is verified in SES."""
    import boto3

    try:
        client = boto3.client("sesv2", region_name=region)
        # Check if the specific email identity exists
        try:
            resp = client.get_email_identity(EmailIdentity=from_email)
            verified = resp.get("VerifiedForSendingStatus", False)
            if verified:
                logger.info("Sender identity '%s' is VERIFIED", from_email)
                return True
            else:
                logger.error("Sender identity '%s' exists but is NOT verified", from_email)
                return False
        except client.exceptions.NotFoundException:
            # Try the domain
            domain = from_email.split("@")[-1]
            try:
                resp = client.get_email_identity(EmailIdentity=domain)
                verified = resp.get("VerifiedForSendingStatus", False)
                if verified:
                    logger.info("Sender domain '%s' is VERIFIED", domain)
                    return True
                else:
                    logger.error("Sender domain '%s' exists but is NOT verified", domain)
                    return False
            except client.exceptions.NotFoundException:
                logger.error(
                    "Neither '%s' nor domain '%s' is registered in SES. "
                    "Go to AWS SES Console → Verified Identities → Create identity.",
                    from_email,
                    domain,
                )
                return False
    except Exception as e:
        logger.error("Sender identity check failed: %s", e)
        return False


# ─── Send test email via boto3 directly ──────────────────────────────────────


def send_test_email_boto3(to_email: str, from_email: str, region: str) -> bool:
    """Send a test email using boto3 directly (bypasses our EmailService)."""
    import boto3

    client = boto3.client("sesv2", region_name=region)

    try:
        response = client.send_email(
            FromEmailAddress=from_email,
            Destination={"ToAddresses": [to_email]},
            Content={
                "Simple": {
                    "Subject": {"Data": "[SES Test] Direct boto3 — Credential Verification"},
                    "Body": {
                        "Text": {
                            "Data": (
                                "This is a direct boto3 SES test.\n\n"
                                "If you received this, your AWS credentials and SES "
                                "configuration are working correctly.\n\n"
                                "— BluOnX SES Integration Test"
                            ),
                        },
                        "Html": {
                            "Data": (
                                "<h2>SES Credential Test — Direct boto3</h2>"
                                "<p>If you received this, your AWS credentials and SES "
                                "configuration are working correctly.</p>"
                                "<hr><p><em>BluOnX SES Integration Test</em></p>"
                            ),
                        },
                    },
                }
            },
        )
        message_id = response.get("MessageId", "unknown")
        logger.info("Direct boto3 send SUCCESS! MessageId: %s", message_id)
        return True
    except Exception as e:
        logger.error("Direct boto3 send FAILED: %s", e)
        return False


# ─── Send test email via our EmailService + MockProvider ─────────────────────


async def send_test_email_mock(to_email: str, from_email: str) -> bool:
    """Send a test email via our EmailService with MockEmailProvider."""
    from app.services.email_service import EmailService, MockEmailProvider

    provider = MockEmailProvider()
    service = EmailService(provider=provider, db_client=None)

    try:
        result = await service.send_email(
            to_email=to_email,
            subject="[Mock Test] EmailService Pipeline Verification",
            html_body=(
                "<h2>Mock Email Test</h2>"
                "<p>This email was sent through the EmailService with MockEmailProvider.</p>"
                "<p>If you see this in logs, the service pipeline works correctly.</p>"
            ),
            plain_text_body=(
                "Mock Email Test\n\n"
                "This email was sent through the EmailService with MockEmailProvider.\n"
                "If you see this in logs, the service pipeline works correctly."
            ),
            from_email=from_email,
            email_type="general",
            recipient_type="user",
        )
        logger.info("Mock send result: status=%s, message_id=%s", result.status, result.message_id)
        return result.status == "sent"
    except Exception as e:
        logger.error("Mock send FAILED: %s", e)
        return False


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Test AWS SES credentials and email sending",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--to", required=True, help="Recipient email (must be verified in SES sandbox)")
    parser.add_argument("--from", dest="from_email", default=None, help="Sender email (default: SES_FROM_EMAIL env var)")
    parser.add_argument("--region", default=None, help="AWS region (default: AWS_REGION or SES_REGION env var)")
    parser.add_argument("--skip-send", action="store_true", help="Only check credentials, don't send email")
    args = parser.parse_args()

    from_email = args.from_email or os.environ.get("SES_FROM_EMAIL", "awaisonfreelance@gmail.com")
    region = args.region or os.environ.get("AWS_REGION") or os.environ.get("SES_REGION", "us-east-1")

    logger.info("=" * 60)
    logger.info("BluOnX SES Integration Test")
    logger.info("=" * 60)
    logger.info("  To:     %s", args.to)
    logger.info("  From:   %s", from_email)
    logger.info("  Region: %s", region)
    logger.info("")

    # Step 1: Mock provider test (no AWS needed)
    logger.info("--- Step 1: Mock EmailService pipeline test ---")
    mock_ok = asyncio.run(send_test_email_mock(args.to, from_email))
    logger.info("Mock pipeline: %s", "PASS" if mock_ok else "FAIL")
    logger.info("")

    # Step 2: Check AWS credentials
    logger.info("--- Step 2: AWS credential check ---")
    creds_ok = check_credentials(region)
    logger.info("Credentials: %s", "PASS" if creds_ok else "FAIL")
    logger.info("")

    if not creds_ok:
        logger.error("Cannot proceed without valid AWS credentials.")
        logger.error("Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your environment or backend/.env")
        sys.exit(1)

    # Step 3: Check sender identity
    logger.info("--- Step 3: Sender identity check ---")
    sender_ok = check_sender_identity(from_email, region)
    logger.info("Sender identity: %s", "PASS" if sender_ok else "FAIL")
    logger.info("")

    if not sender_ok:
        sys.exit(1)

    if args.skip_send:
        logger.info("--skip-send flag set, skipping actual email send.")
        sys.exit(0)

    # Step 4: Send real email via boto3
    logger.info("--- Step 4: Send test email via boto3 ---")
    send_ok = send_test_email_boto3(args.to, from_email, region)
    logger.info("boto3 send: %s", "PASS" if send_ok else "FAIL")
    logger.info("")

    # Summary
    logger.info("=" * 60)
    all_pass = mock_ok and creds_ok and sender_ok and send_ok
    if all_pass:
        logger.info("ALL CHECKS PASSED — SES is ready!")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Set EMAIL_PROVIDER=ses in backend/.env")
        logger.info("  2. Implement SESEmailProvider in email_providers/ses_provider.py")
        logger.info("  3. Check your inbox at %s for the test email", args.to)
    else:
        logger.error("SOME CHECKS FAILED — see errors above")
        sys.exit(1)


if __name__ == "__main__":
    main()
