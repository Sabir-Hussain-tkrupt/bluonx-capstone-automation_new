"""
Tests for PUT /v1/bid-invitations/{invitation_id}/status.

PMs may manually set invitation status to 'declined', 'expired', or
'no_response'. The statuses 'sent', 'opened', and 'submitted' are
system-managed and must be rejected with 400.

Token revocation: a successful PM-driven status transition must also
hard-revoke all magic_link_tokens for that invitation
(is_used=True, revoked_at=NOW(), revoked_by=current_user_id).
Rejected transitions (400/409) must NOT touch tokens.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# Import will fail until implementation lands — expected for test-first.
from app.services.invitation_tracking_service import (
    InvalidStatusError,
    InvitationNotFoundError,
    TerminalStatusError,
    update_invitation_status,
)

from .conftest import (
    INVITATION_IDS,
    NONEXISTENT_INVITATION_ID,
    build_chain,
)

CURRENT_USER_ID = uuid4()


def _client_with_invitation(invitation: dict, updated_invitation: dict = None):
    """Return a mock client that finds the given invitation and stages
    `updated_invitation` as the result of the update."""
    client = MagicMock()
    result_row = updated_invitation or invitation

    def table_side_effect(name):
        if name == "bid_invitations":
            chain = build_chain(data=[invitation])
            # The .update() chain path returns the updated row
            chain.update.return_value = chain
            chain.execute.return_value = MagicMock(data=[result_row])
            return chain
        return build_chain(data=[])

    client.table.side_effect = table_side_effect
    return client


@pytest.fixture()
def base_invitation():
    return {
        "id": str(INVITATION_IDS["sent"]),
        "bid_package_id": "00000000-0000-0000-0000-000000000001",
        "vendor_id": "00000000-0000-0000-0000-000000000002",
        "vendor_contact_id": "00000000-0000-0000-0000-000000000003",
        "status": "sent",
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "opened_at": None,
        "responded_at": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class TestPMCanSetAllowedStatuses:
    """PM can update status to declined, expired, no_response."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("new_status", ["declined", "expired", "no_response"])
    async def test_sets_allowed_status(self, base_invitation, new_status):
        updated = {**base_invitation, "status": new_status}
        client = _client_with_invitation(base_invitation, updated)

        result = await update_invitation_status(
            invitation_id=INVITATION_IDS["sent"],
            new_status=new_status,
            current_user_id=CURRENT_USER_ID,
            db=client,
        )

        assert result["status"] == new_status


class TestRejectsSystemManagedStatuses:
    """'sent', 'opened', 'submitted' cannot be set by PM → 400."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_status", ["sent", "opened", "submitted"])
    async def test_rejects_system_managed_status(self, base_invitation, bad_status):
        client = _client_with_invitation(base_invitation)

        with pytest.raises(InvalidStatusError) as exc_info:
            await update_invitation_status(
                invitation_id=INVITATION_IDS["sent"],
                new_status=bad_status,
                current_user_id=CURRENT_USER_ID,
                db=client,
            )

        assert exc_info.value.status_code == 400


class TestRejectsUnknownStatus:
    """Unknown status strings (not in the CHECK constraint) → 400."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_status", ["archived", "pending", "", "DECLINED"])
    async def test_rejects_unknown_status(self, base_invitation, bad_status):
        client = _client_with_invitation(base_invitation)

        with pytest.raises(InvalidStatusError) as exc_info:
            await update_invitation_status(
                invitation_id=INVITATION_IDS["sent"],
                new_status=bad_status,
                current_user_id=CURRENT_USER_ID,
                db=client,
            )

        assert exc_info.value.status_code == 400


class TestNonexistentInvitation:
    """Nonexistent invitation_id → 404."""

    @pytest.mark.asyncio
    async def test_raises_not_found(self):
        client = MagicMock()

        def table_side_effect(name):
            return build_chain(data=[])

        client.table.side_effect = table_side_effect

        with pytest.raises(InvitationNotFoundError):
            await update_invitation_status(
                invitation_id=NONEXISTENT_INVITATION_ID,
                new_status="declined",
                current_user_id=CURRENT_USER_ID,
                db=client,
            )


class TestRejectsTransitionFromSubmitted:
    """Submitted is terminal — any PM-requested transition returns 409."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("new_status", ["declined", "expired", "no_response"])
    async def test_rejects_when_current_status_is_submitted(
        self, base_invitation, new_status
    ):
        submitted = {**base_invitation, "status": "submitted"}
        client = _client_with_invitation(submitted)

        with pytest.raises(TerminalStatusError) as exc_info:
            await update_invitation_status(
                invitation_id=INVITATION_IDS["sent"],
                new_status=new_status,
                current_user_id=CURRENT_USER_ID,
                db=client,
            )

        assert exc_info.value.status_code == 409


class TestResponseContainsUpdatedInvitation:
    """Response body contains the updated invitation row."""

    @pytest.mark.asyncio
    async def test_response_reflects_new_status(self, base_invitation):
        updated = {**base_invitation, "status": "declined"}
        client = _client_with_invitation(base_invitation, updated)

        result = await update_invitation_status(
            invitation_id=INVITATION_IDS["sent"],
            new_status="declined",
            current_user_id=CURRENT_USER_ID,
            db=client,
        )

        assert result["id"] == str(INVITATION_IDS["sent"])
        assert result["status"] == "declined"
        assert "updated_at" in result


# ── Token revocation helpers ──────────────────────────────────────────────


def _client_with_token_capture(
    invitation: dict, updated_invitation: dict = None
) -> tuple[MagicMock, list[dict]]:
    """Mock client that returns the invitation on SELECT, captures any
    magic_link_tokens UPDATE payloads, and returns the updated row on the
    bid_invitations UPDATE."""
    client = MagicMock()
    result_row = updated_invitation or invitation
    token_updates: list[dict] = []

    def table_side_effect(name: str):
        if name == "bid_invitations":
            # SELECT path (.single().execute()) returns the existing row.
            # UPDATE path (.update(payload).eq(...).execute()) returns updated row.
            chain = build_chain(data=[invitation])
            chain.update.return_value = build_chain(data=[result_row])
            return chain

        if name == "magic_link_tokens":
            token_chain = build_chain(data=[])

            def capture_token_update(payload):
                token_updates.append(payload)
                return token_chain

            token_chain.update.side_effect = capture_token_update
            return token_chain

        return build_chain(data=[])

    client.table.side_effect = table_side_effect
    return client, token_updates


# ── Token revocation tests ────────────────────────────────────────────────


class TestTokenRevocationOnDecline:
    """A successful PM status update must hard-revoke all magic-link tokens
    for that invitation. Rejected transitions must NOT touch tokens."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("new_status", ["declined", "expired", "no_response"])
    async def test_revokes_tokens_for_all_pm_settable_statuses(
        self, base_invitation, new_status
    ):
        """All three PM-settable statuses trigger token revocation."""
        updated = {**base_invitation, "status": new_status}
        client, token_updates = _client_with_token_capture(base_invitation, updated)

        await update_invitation_status(
            invitation_id=INVITATION_IDS["sent"],
            new_status=new_status,
            current_user_id=CURRENT_USER_ID,
            db=client,
        )

        assert len(token_updates) == 1
        payload = token_updates[0]
        assert payload["is_used"] is True
        assert "revoked_at" in payload
        assert payload["revoked_by"] == str(CURRENT_USER_ID)

    @pytest.mark.asyncio
    async def test_revoked_by_reflects_calling_user(self, base_invitation):
        """revoked_by is the UUID of the user who triggered the decline,
        not a hardcoded value."""
        other_user = uuid4()
        updated = {**base_invitation, "status": "declined"}
        client, token_updates = _client_with_token_capture(base_invitation, updated)

        await update_invitation_status(
            invitation_id=INVITATION_IDS["sent"],
            new_status="declined",
            current_user_id=other_user,
            db=client,
        )

        assert token_updates[0]["revoked_by"] == str(other_user)

    @pytest.mark.asyncio
    async def test_tokens_not_revoked_when_status_rejected_400(
        self, base_invitation
    ):
        """If the requested status is system-managed (400), no token write
        should occur — the validation gate fires before any DB mutation."""
        client, token_updates = _client_with_token_capture(base_invitation)

        with pytest.raises(InvalidStatusError):
            await update_invitation_status(
                invitation_id=INVITATION_IDS["sent"],
                new_status="opened",  # system-managed → 400
                current_user_id=CURRENT_USER_ID,
                db=client,
            )

        assert len(token_updates) == 0

    @pytest.mark.asyncio
    async def test_tokens_not_revoked_when_terminal_409(self, base_invitation):
        """If the invitation is already submitted (409), no token write."""
        submitted = {**base_invitation, "status": "submitted"}
        client, token_updates = _client_with_token_capture(submitted)

        with pytest.raises(TerminalStatusError):
            await update_invitation_status(
                invitation_id=INVITATION_IDS["sent"],
                new_status="declined",
                current_user_id=CURRENT_USER_ID,
                db=client,
            )

        assert len(token_updates) == 0
