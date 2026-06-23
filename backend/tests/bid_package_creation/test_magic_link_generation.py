"""
Magic link token generation and security tests.

Verifies cryptographic properties: URL-safe tokens, SHA-256 hashing, raw token
never stored, correct expiration, and uniqueness per vendor.

Tokens are generated in Python and passed to the atomic creation RPC as hashes
(p_vendors[].token_hash); the raw token only ever lives in the emailed URL. These
tests therefore inspect the RPC payload + the emailed link, not table inserts.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import quote
from uuid import uuid4

import pytest

from app.services.email_service import EmailSendResult

from .conftest import (
    BID_TEMPLATE_ID,
    PM_USER_ID,
    PORTAL_BASE_URL,
    TASK_ID,
    VENDOR_CONTACT_IDS,
    VENDOR_IDS,
)

from app.services.bid_package_service import create_bid_package_with_invitations


# URL-safe base64 alphabet: A-Z, a-z, 0-9, -, _
_URL_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _rpc_create_params(mock_supabase) -> dict:
    """Return the single creation-RPC call's params."""
    calls = [
        c
        for c in mock_supabase.rpc.call_args_list
        if c.args and c.args[0] == "fn_create_bid_package_with_invitations"
    ]
    assert calls, "creation RPC should have been called"
    return calls[-1].args[1]


def _single_vendor_payload(future_deadline) -> dict:
    return {
        "task_id": str(TASK_ID),
        "bid_template_id": str(BID_TEMPLATE_ID),
        "deadline": future_deadline.isoformat(),
        "project_document_ids": [],
        "vendor_selections": [
            {"vendor_id": str(VENDOR_IDS[0]), "vendor_contact_id": str(VENDOR_CONTACT_IDS[0])},
        ],
    }


def _capture_email_tokens(mock_email_service) -> list[str]:
    """Wire the email mock to extract the raw token from each magic link."""
    raw_tokens: list[str] = []

    async def capture_email_send(**kwargs):
        html = kwargs.get("html_body", "")
        match = re.search(r"/bid/([A-Za-z0-9_-]+)", html)
        if match:
            raw_tokens.append(match.group(1))
        return EmailSendResult(message_id=f"mock-{uuid4()}", status="sent", error=None)

    mock_email_service.send_email.side_effect = capture_email_send
    return raw_tokens


class TestTokenURLSafety:
    """Raw tokens must be URL-safe for use in magic link URLs."""

    @pytest.mark.asyncio
    async def test_raw_token_is_url_safe(
        self, mock_supabase, mock_email_service, mock_template_renderer, future_deadline,
    ):
        """Raw token contains only URL-safe characters (no encoding needed)."""
        raw_tokens = _capture_email_tokens(mock_email_service)

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=_single_vendor_payload(future_deadline),
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
            assert quote(token, safe="") == token, f"Token '{token}' requires URL encoding"


class TestTokenHashing:
    """Token passed to the DB must be the SHA-256 hash of the raw token."""

    @pytest.mark.asyncio
    async def test_token_hash_is_sha256_of_raw_token(
        self, mock_supabase, mock_email_service, mock_template_renderer, future_deadline,
    ):
        """token_hash sent to the RPC equals SHA-256 of the raw token in the email."""
        raw_tokens = _capture_email_tokens(mock_email_service)

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=_single_vendor_payload(future_deadline),
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(raw_tokens) == 1
        vendors = _rpc_create_params(mock_supabase)["p_vendors"]
        assert len(vendors) == 1

        expected_hash = hashlib.sha256(raw_tokens[0].encode()).hexdigest()
        assert vendors[0]["token_hash"] == expected_hash

    @pytest.mark.asyncio
    async def test_raw_token_not_passed_to_database(
        self, mock_supabase, mock_email_service, mock_template_renderer, future_deadline,
    ):
        """The raw token must never appear in the RPC payload — only the hash."""
        raw_tokens = _capture_email_tokens(mock_email_service)

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=_single_vendor_payload(future_deadline),
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(raw_tokens) >= 1
        vendors = _rpc_create_params(mock_supabase)["p_vendors"]
        for raw_token in raw_tokens:
            for entry in vendors:
                for key, value in entry.items():
                    assert str(value) != raw_token, (
                        f"Raw token found in RPC field '{key}': {value}"
                    )


class TestTokenExpiration:
    """Token expiry is driven by the bid package deadline."""

    @pytest.mark.asyncio
    async def test_deadline_passed_to_rpc_for_token_expiry(
        self, mock_supabase, mock_email_service, mock_template_renderer, future_deadline,
    ):
        """The RPC receives p_deadline, which it uses as every token's expires_at."""
        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=_single_vendor_payload(future_deadline),
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        params = _rpc_create_params(mock_supabase)
        assert params["p_deadline"] == future_deadline.isoformat()


class TestTokenPayloadShape:
    """Each vendor entry carries only the hash + identity, nothing sensitive."""

    @pytest.mark.asyncio
    async def test_vendor_entry_has_expected_keys_only(
        self, mock_supabase, mock_email_service, mock_template_renderer, future_deadline,
    ):
        """p_vendors entries contain exactly vendor_id, vendor_contact_id, token_hash."""
        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=_single_vendor_payload(future_deadline),
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        vendors = _rpc_create_params(mock_supabase)["p_vendors"]
        assert vendors, "at least one vendor entry expected"
        for entry in vendors:
            assert set(entry.keys()) == {"vendor_id", "vendor_contact_id", "token_hash"}


class TestMagicLinkURLFormat:
    """Magic link URL must follow the expected format."""

    @pytest.mark.asyncio
    async def test_magic_link_url_format(
        self, mock_supabase, mock_email_service, mock_template_renderer, future_deadline,
    ):
        """Magic link URL must be {PORTAL_BASE_URL}/bid/{raw_token}."""
        rendered_urls: list[str] = []

        def capture_render(template_name, context):
            if "magic_link_url" in context:
                rendered_urls.append(context["magic_link_url"])
            return "<html><body>Bid Invitation</body></html>"

        mock_template_renderer.render.side_effect = capture_render

        await create_bid_package_with_invitations(
            task_id=TASK_ID,
            payload=_single_vendor_payload(future_deadline),
            created_by=PM_USER_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(rendered_urls) >= 1
        for url in rendered_urls:
            assert url.startswith(f"{PORTAL_BASE_URL}/bid/")
            assert len(url.split("/bid/")[-1]) > 0, "Token part of URL is empty"


class TestTokenUniqueness:
    """Each vendor must receive a unique token."""

    @pytest.mark.asyncio
    async def test_each_vendor_gets_unique_token(
        self, mock_supabase, mock_email_service, mock_template_renderer, future_deadline,
    ):
        """No two vendor entries share the same token hash."""
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

        vendors = _rpc_create_params(mock_supabase)["p_vendors"]
        assert len(vendors) == 3
        hashes = [v["token_hash"] for v in vendors]
        assert len(set(hashes)) == 3, f"Expected 3 unique token hashes: {hashes}"
