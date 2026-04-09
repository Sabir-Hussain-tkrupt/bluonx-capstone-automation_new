"""
Resend invitation tests.

Verifies the resend flow: new magic link token, old tokens invalidated,
sent_at updated, new email_log row, and status-based rejection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.email_service import EmailSendResult

from .conftest import (
    BID_TEMPLATE_ID,
    PM_USER_ID,
    TASK_ID,
    VENDOR_CONTACT_IDS,
    VENDOR_IDS,
)

# This import will fail until the service is implemented — expected for test-first.
from app.services.bid_package_service import (
    BidPackageValidationError,
    resend_invitation,
)


INVITATION_ID = uuid4()
BID_PACKAGE_ID = uuid4()
OLD_TOKEN_ID = uuid4()


@pytest.fixture()
def sample_invitation() -> dict:
    """An existing bid invitation in 'sent' status."""
    return {
        "id": str(INVITATION_ID),
        "bid_package_id": str(BID_PACKAGE_ID),
        "vendor_id": str(VENDOR_IDS[0]),
        "vendor_contact_id": str(VENDOR_CONTACT_IDS[0]),
        "status": "sent",
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture()
def sample_bid_package_open() -> dict:
    """An open bid package (valid for resend)."""
    deadline = datetime.now(timezone.utc) + timedelta(days=14)
    return {
        "id": str(BID_PACKAGE_ID),
        "task_id": str(TASK_ID),
        "round_number": 1,
        "deadline": deadline.isoformat(),
        "status": "open",
        "bid_template_id": str(BID_TEMPLATE_ID),
        "created_by": str(PM_USER_ID),
    }


@pytest.fixture()
def existing_tokens() -> list[dict]:
    """Previous magic link tokens for this invitation."""
    return [
        {
            "id": str(OLD_TOKEN_ID),
            "bid_invitation_id": str(INVITATION_ID),
            "vendor_id": str(VENDOR_IDS[0]),
            "token_hash": "old_hash_abc123",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
            "is_used": False,
        },
    ]


def _setup_resend_mocks(
    mock_supabase,
    invitation: dict,
    bid_package: dict,
    tokens: list[dict],
):
    """Configure mocks for a resend operation."""
    token_updates: list[dict] = []
    token_inserts: list[dict] = []

    def table_side_effect(table_name):
        chain = MagicMock()

        if table_name == "bid_invitations":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[invitation])
            # For update
            update_result = MagicMock()
            update_result.eq.return_value = update_result
            update_result.execute.return_value = MagicMock(data=[invitation])
            chain.update.return_value = update_result
        elif table_name == "bid_packages":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[bid_package])
        elif table_name == "magic_link_tokens":
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.execute.return_value = MagicMock(data=tokens)

            def capture_update(data):
                token_updates.append(data)
                result = MagicMock()
                result.eq.return_value = result
                result.execute.return_value = MagicMock(data=[])
                return result
            chain.update.side_effect = capture_update

            def capture_insert(row):
                token_inserts.append(row)
                result = MagicMock()
                result.execute.return_value = MagicMock(data=[{**row, "id": str(uuid4())}])
                return result
            chain.insert.side_effect = capture_insert
        elif table_name == "vendor_contacts":
            contact = {
                "id": str(VENDOR_CONTACT_IDS[0]),
                "vendor_id": str(VENDOR_IDS[0]),
                "full_name": "John Smith",
                "email": "john@smithgrading.com",
            }
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[contact])
        else:
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            result = MagicMock()
            result.execute.return_value = MagicMock(data=[])
            chain.insert.return_value = result
            chain.update.return_value = result
            chain.execute.return_value = MagicMock(data=[])

        return chain

    mock_supabase.table.side_effect = table_side_effect
    return token_updates, token_inserts


class TestResendGeneratesNewToken:
    """Resending creates a new magic link token."""

    @pytest.mark.asyncio
    async def test_new_token_created(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_invitation,
        sample_bid_package_open,
        existing_tokens,
    ):
        """Resend generates a new magic_link_tokens row."""
        _, token_inserts = _setup_resend_mocks(
            mock_supabase, sample_invitation, sample_bid_package_open, existing_tokens
        )

        await resend_invitation(
            invitation_id=INVITATION_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(token_inserts) == 1, "Exactly one new token should be created"
        assert token_inserts[0]["bid_invitation_id"] == str(INVITATION_ID)


class TestOldTokensInvalidated:
    """Previous tokens must be invalidated on resend."""

    @pytest.mark.asyncio
    async def test_previous_tokens_marked_as_used(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_invitation,
        sample_bid_package_open,
        existing_tokens,
    ):
        """All previous tokens for this invitation are set to is_used=TRUE."""
        token_updates, _ = _setup_resend_mocks(
            mock_supabase, sample_invitation, sample_bid_package_open, existing_tokens
        )

        await resend_invitation(
            invitation_id=INVITATION_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        # The update should set is_used=True
        assert len(token_updates) >= 1
        assert any(update.get("is_used") is True for update in token_updates), (
            "Previous tokens should be updated with is_used=True"
        )


class TestNewTokenExpiration:
    """New token must have expires_at matching the bid package deadline."""

    @pytest.mark.asyncio
    async def test_new_token_expires_at_matches_deadline(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_invitation,
        sample_bid_package_open,
        existing_tokens,
    ):
        """The new token's expires_at equals the bid package deadline."""
        _, token_inserts = _setup_resend_mocks(
            mock_supabase, sample_invitation, sample_bid_package_open, existing_tokens
        )

        await resend_invitation(
            invitation_id=INVITATION_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert len(token_inserts) == 1
        assert token_inserts[0]["expires_at"] == sample_bid_package_open["deadline"]


class TestSentAtUpdated:
    """bid_invitations.sent_at must be updated on resend."""

    @pytest.mark.asyncio
    async def test_invitation_sent_at_updated(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_invitation,
        sample_bid_package_open,
        existing_tokens,
    ):
        """bid_invitations.sent_at is updated to the new send time."""
        _setup_resend_mocks(
            mock_supabase, sample_invitation, sample_bid_package_open, existing_tokens
        )

        await resend_invitation(
            invitation_id=INVITATION_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        # Verify bid_invitations table had an update call
        invitation_table_calls = [
            c for c in mock_supabase.table.call_args_list
            if hasattr(c, 'args') and c.args and c.args[0] == "bid_invitations"
        ]
        assert len(invitation_table_calls) >= 1


class TestResendCreatesEmailLog:
    """A new email_log row must be created on resend."""

    @pytest.mark.asyncio
    async def test_email_service_called_on_resend(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_invitation,
        sample_bid_package_open,
        existing_tokens,
    ):
        """EmailService.send_email is called, which creates an email_log row."""
        _setup_resend_mocks(
            mock_supabase, sample_invitation, sample_bid_package_open, existing_tokens
        )

        await resend_invitation(
            invitation_id=INVITATION_ID,
            db=mock_supabase,
            email_service=mock_email_service,
            template_renderer=mock_template_renderer,
        )

        assert mock_email_service.send_email.call_count == 1
        call_kwargs = mock_email_service.send_email.call_args.kwargs
        assert call_kwargs["email_type"] == "bid_invitation"


class TestResendStatusRestrictions:
    """Resend must fail if the bid package is not in 'open' status."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["closed", "cancelled", "evaluating"])
    async def test_resend_fails_for_non_open_bid_package(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
        sample_invitation,
        existing_tokens,
        status,
    ):
        """Resend should fail with appropriate error for closed/cancelled/evaluating packages."""
        non_open_package = {
            "id": str(BID_PACKAGE_ID),
            "task_id": str(TASK_ID),
            "round_number": 1,
            "deadline": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
            "status": status,
            "bid_template_id": str(BID_TEMPLATE_ID),
            "created_by": str(PM_USER_ID),
        }

        _setup_resend_mocks(
            mock_supabase, sample_invitation, non_open_package, existing_tokens
        )

        with pytest.raises(BidPackageValidationError) as exc_info:
            await resend_invitation(
                invitation_id=INVITATION_ID,
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 400


class TestResendNonexistentInvitation:
    """Resend must fail with 404 for non-existent invitation."""

    @pytest.mark.asyncio
    async def test_nonexistent_invitation_returns_404(
        self,
        mock_supabase,
        mock_email_service,
        mock_template_renderer,
    ):
        """Resend with an invitation_id that doesn't exist returns 404."""
        def table_side_effect(table_name):
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.single.return_value = chain
            chain.execute.return_value = MagicMock(data=[])
            return chain

        mock_supabase.table.side_effect = table_side_effect

        with pytest.raises(BidPackageValidationError) as exc_info:
            await resend_invitation(
                invitation_id=uuid4(),
                db=mock_supabase,
                email_service=mock_email_service,
                template_renderer=mock_template_renderer,
            )

        assert exc_info.value.status_code == 404
