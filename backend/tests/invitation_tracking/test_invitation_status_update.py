"""
Tests for PUT /v1/bid-invitations/{invitation_id}/status.

PMs may manually set invitation status to 'declined', 'expired', or
'no_response'. The statuses 'sent', 'opened', and 'submitted' are
system-managed and must be rejected with 400.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

# Import will fail until implementation lands — expected for test-first.
from app.services.invitation_tracking_service import (
    InvalidStatusError,
    InvitationNotFoundError,
    update_invitation_status,
)

from .conftest import (
    INVITATION_IDS,
    NONEXISTENT_INVITATION_ID,
    build_chain,
)


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
                db=client,
            )


class TestResponseContainsUpdatedInvitation:
    """Response body contains the updated invitation row."""

    @pytest.mark.asyncio
    async def test_response_reflects_new_status(self, base_invitation):
        updated = {**base_invitation, "status": "declined"}
        client = _client_with_invitation(base_invitation, updated)

        result = await update_invitation_status(
            invitation_id=INVITATION_IDS["sent"],
            new_status="declined",
            db=client,
        )

        assert result["id"] == str(INVITATION_IDS["sent"])
        assert result["status"] == "declined"
        assert "updated_at" in result
