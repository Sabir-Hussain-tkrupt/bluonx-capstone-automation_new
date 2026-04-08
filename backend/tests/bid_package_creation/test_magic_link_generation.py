"""
Magic link token generation and security tests.

Verifies cryptographic properties: URL-safe tokens, SHA-256 hashing,
raw token never stored, correct expiration, and uniqueness per vendor.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call
from urllib.parse import quote
from uuid import uuid4

import pytest

from app.services.email_service import EmailSendResult

from .conftest import (
    BID_TEMPLATE_ID,
    DOC_IDS,
    PM_USER_ID,
    PORTAL_BASE_URL,
    PROJECT_ID,
    TASK_ID,
    VENDOR_CONTACT_IDS,
    VENDOR_IDS,
)

# This import will fail until the service is implemented — expected for test-first.
from app.services.bid_package_service import create_bid_package_with_invitations


# URL-safe base64 alphabet: A-Z, a-z, 0-9, -, _
_URL_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _setup_successful_creation(mock_supabase, deadline_iso: str):
    """Configure mocks for a successful bid package creation that captures token inserts."""
    bid_package_id = uuid4()

    # Collect all magic_link_tokens inserts for assertion
    token_inserts: list[dict] = []
    invitation_inserts: list[dict] = []

    original_table = mock_supabase.table

    def table_side_effect(table_name):
        chain = MagicMock()

        if table_name == "bid_packages":
            insert_result = MagicMock()
            insert_result.execute.return_value = MagicMock(data=[{
                "id": str(bid_package_id),
                "task_id": str(TASK_ID),
                "round_number": 1,
                "deadline": deadline_iso,
                "status": "open",
                "bid_template_id": str(BID_TEMPLATE_ID),
                "created_by": str(PM_USER_ID),
            }])
            chain.insert.return_value = insert_result
        elif table_name == "magic_link_tokens":
            def capture_token_insert(row):
                token_inserts.append(row)
                result = MagicMock()
                result.execute.return_value = MagicMock(data=[{**row, "id": str(uuid4())}])
                return result
            chain.insert.side_effect = capture_token_insert
        elif table_name == "bid_invitations":
            def capture_invitation_insert(row):
                invitation_inserts.append(row)
                result = MagicMock()
                result.execute.return_value = MagicMock(data=[{**row, "id": str(uuid4())}])
                return result
            chain.insert.side_effect = capture_invitation_insert
        else:
            result = MagicMock()
            result.execute.return_value = MagicMock(data=[])
            chain.insert.return_value = result
            chain.select.return_value = result
            chain.update.return_value = result
            result.eq.return_value = result

        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.is_.return_value = chain
        chain.single.return_value = chain
        if not hasattr(chain.execute, 'return_value') or chain.execute.return_value is None:
            chain.execute.return_value = MagicMock(data=[])

        return chain

    mock_supabase.table.side_effect = table_side_effect

    return bid_package_id, token_inserts, invitation_inserts


class TestTokenURLSafety:
    """Raw tokens must be URL-safe for use in magic link URLs."""

    @pytest.mark.asyncio
    async def test_raw_token_is_url_safe(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        future_deadline,
    ):
        """Raw token contains only URL-safe characters (no encoding needed)."""
        _, token_inserts, _ = _setup_successful_creation(
            mock_supabase, future_deadline.isoformat()
        )

        # Track raw tokens from email calls
        raw_tokens: list[str] = []

        async def capture_email_send(**kwargs):
            # The magic link URL should be in the HTML body
            html = kwargs.get("html_body", "")
            # Extract token from URL pattern: /bid/{token}
            match = re.search(r"/bid/([A-Za-z0-9_-]+)", html)
            if match:
                raw_tokens.append(match.group(1))
            return EmailSendResult(message_id=f"mock-{uuid4()}", status="sent", error=None)

        mock_email_service.send_email.side_effect = capture_email_send

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(raw_tokens) >= 1, "At least one raw token should be extracted from emails"
        for token in raw_tokens:
            assert _URL_SAFE_PATTERN.match(token), (
                f"Token '{token}' contains non-URL-safe characters"
            )
            # Verify URL encoding doesn't change the token
            assert quote(token, safe="") == token, (
                f"Token '{token}' requires URL encoding"
            )


class TestTokenHashing:
    """Token stored in DB must be SHA-256 hash of the raw token."""

    @pytest.mark.asyncio
    async def test_token_hash_is_sha256_of_raw_token(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        future_deadline,
    ):
        """token_hash in DB equals SHA-256 hex digest of the raw token sent in email."""
        _, token_inserts, _ = _setup_successful_creation(
            mock_supabase, future_deadline.isoformat()
        )

        raw_tokens: list[str] = []

        async def capture_email_send(**kwargs):
            html = kwargs.get("html_body", "")
            match = re.search(r"/bid/([A-Za-z0-9_-]+)", html)
            if match:
                raw_tokens.append(match.group(1))
            return EmailSendResult(message_id=f"mock-{uuid4()}", status="sent", error=None)

        mock_email_service.send_email.side_effect = capture_email_send

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(raw_tokens) >= 1
        assert len(token_inserts) >= 1

        # The hash stored in DB must match SHA-256 of the raw token
        for raw_token, insert_row in zip(raw_tokens, token_inserts):
            expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            assert insert_row["token_hash"] == expected_hash, (
                f"DB hash {insert_row['token_hash']} != SHA-256({raw_token}) = {expected_hash}"
            )

    @pytest.mark.asyncio
    async def test_raw_token_not_stored_in_database(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        future_deadline,
    ):
        """The raw token must never appear in any database insert — only the hash."""
        _, token_inserts, _ = _setup_successful_creation(
            mock_supabase, future_deadline.isoformat()
        )

        raw_tokens: list[str] = []

        async def capture_email_send(**kwargs):
            html = kwargs.get("html_body", "")
            match = re.search(r"/bid/([A-Za-z0-9_-]+)", html)
            if match:
                raw_tokens.append(match.group(1))
            return EmailSendResult(message_id=f"mock-{uuid4()}", status="sent", error=None)

        mock_email_service.send_email.side_effect = capture_email_send

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(raw_tokens) >= 1

        # Check that raw token does not appear in any field of the DB insert
        for raw_token in raw_tokens:
            for insert_row in token_inserts:
                for key, value in insert_row.items():
                    assert str(value) != raw_token, (
                        f"Raw token found in DB field '{key}': {value}"
                    )


class TestTokenExpiration:
    """Token expires_at must match the bid package deadline."""

    @pytest.mark.asyncio
    async def test_expires_at_equals_bid_package_deadline(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        future_deadline,
    ):
        """magic_link_tokens.expires_at must equal bid_packages.deadline."""
        _, token_inserts, _ = _setup_successful_creation(
            mock_supabase, future_deadline.isoformat()
        )

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(token_inserts) >= 1
        for insert_row in token_inserts:
            assert insert_row["expires_at"] == future_deadline.isoformat(), (
                f"Token expires_at {insert_row['expires_at']} != deadline {future_deadline.isoformat()}"
            )


class TestTokenInitialState:
    """Tokens must be created in the correct initial state."""

    @pytest.mark.asyncio
    async def test_is_used_is_false_on_creation(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        future_deadline,
    ):
        """is_used must be FALSE when the token is first created."""
        _, token_inserts, _ = _setup_successful_creation(
            mock_supabase, future_deadline.isoformat()
        )

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(token_inserts) >= 1
        for insert_row in token_inserts:
            assert insert_row.get("is_used") is False, (
                "Token is_used should be False on creation"
            )


class TestMagicLinkURLFormat:
    """Magic link URL must follow the expected format."""

    @pytest.mark.asyncio
    async def test_magic_link_url_format(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        future_deadline,
    ):
        """Magic link URL must be {PORTAL_BASE_URL}/bid/{raw_token}."""
        _, token_inserts, _ = _setup_successful_creation(
            mock_supabase, future_deadline.isoformat()
        )

        rendered_urls: list[str] = []

        def capture_render(template_name, context):
            if "magic_link_url" in context:
                rendered_urls.append(context["magic_link_url"])
            return "<html><body>Bid Invitation</body></html>"

        mock_template_renderer.render.side_effect = capture_render

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
            ],
        }

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(rendered_urls) >= 1
        for url in rendered_urls:
            assert url.startswith(f"{PORTAL_BASE_URL}/bid/"), (
                f"URL {url} doesn't match expected format {PORTAL_BASE_URL}/bid/{{token}}"
            )
            # Extract token part and verify it's non-empty
            token_part = url.split("/bid/")[-1]
            assert len(token_part) > 0, "Token part of URL is empty"


class TestTokenUniqueness:
    """Each vendor must receive a unique token."""

    @pytest.mark.asyncio
    async def test_each_vendor_gets_unique_token(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        future_deadline,
    ):
        """No two invitations share the same token."""
        _, token_inserts, _ = _setup_successful_creation(
            mock_supabase, future_deadline.isoformat()
        )

        payload = {
            "task_id": str(TASK_ID),
            "bid_template_id": str(BID_TEMPLATE_ID),
            "deadline": future_deadline.isoformat(),
            "project_document_ids": [],
            "vendor_selections": [
                {"vendor_id": str(VENDOR_IDS[i]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[i])}
                for i in range(3)
            ],
        }

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=payload,
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(token_inserts) == 3, "Should have 3 token inserts for 3 vendors"

        hashes = [row["token_hash"] for row in token_inserts]
        assert len(set(hashes)) == 3, (
            f"Expected 3 unique token hashes, got {len(set(hashes))}: {hashes}"
        )
