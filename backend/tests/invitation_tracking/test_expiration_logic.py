"""
Tests for the expire_overdue_invitations() utility.

Pure service function. Given a bid_package_id, if the deadline has passed
and the package is still 'open', it flips all 'sent'/'opened' invitations
to 'expired' and the package status to 'closed'. It does not touch
'submitted' or 'declined' rows. It is a no-op if the deadline hasn't
passed or the package is already 'closed' or 'cancelled'.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Import will fail until implementation lands — expected for test-first.
from app.services.invitation_tracking_service import expire_overdue_invitations

from .conftest import BID_PACKAGE_ID, build_chain


def _build_client(
    bid_package: dict,
    invitations: list[dict],
    updates_captured: list[dict],
) -> MagicMock:
    client = MagicMock()

    def table_side_effect(name):
        if name == "bid_packages":
            chain = build_chain(data=[bid_package])
        elif name == "bid_invitations":
            chain = build_chain(data=invitations)
        else:
            chain = build_chain(data=[])

        original_update = chain.update

        def capture(payload):
            updates_captured.append({"table": name, "payload": payload})
            return original_update(payload)

        chain.update.side_effect = capture
        return chain

    client.table.side_effect = table_side_effect
    return client


class TestExpiresOverdueInvitations:
    """sent/opened invitations are expired when deadline has passed."""

    @pytest.mark.asyncio
    async def test_sent_and_opened_become_expired(
        self,
        sample_bid_package_past_deadline,
        sample_invitations_mixed_statuses,
        updates_captured,
    ):
        client = _build_client(
            sample_bid_package_past_deadline,
            sample_invitations_mixed_statuses,
            updates_captured,
        )

        result = await expire_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        assert result["expired_count"] == 2  # 'sent' + 'opened'
        assert result["package_closed"] is True

        # At least one bid_invitations update with status='expired'
        invitation_updates = [
            u for u in updates_captured
            if u["table"] == "bid_invitations"
            and u["payload"].get("status") == "expired"
        ]
        assert len(invitation_updates) >= 1


class TestDoesNotTouchFinalizedRows:
    """submitted/declined invitations must not be modified."""

    @pytest.mark.asyncio
    async def test_submitted_and_declined_untouched(
        self,
        sample_bid_package_past_deadline,
        sample_invitations_mixed_statuses,
        updates_captured,
    ):
        client = _build_client(
            sample_bid_package_past_deadline,
            sample_invitations_mixed_statuses,
            updates_captured,
        )

        await expire_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        # The update payload for bid_invitations should only ever be
        # status='expired' — never 'submitted' or 'declined'.
        invitation_update_payloads = [
            u["payload"] for u in updates_captured
            if u["table"] == "bid_invitations"
        ]
        for payload in invitation_update_payloads:
            status = payload.get("status")
            if status is not None:
                assert status == "expired"


class TestUpdatesBidPackageToClosed:
    """bid_packages.status flips from 'open' to 'closed'."""

    @pytest.mark.asyncio
    async def test_package_status_closed(
        self,
        sample_bid_package_past_deadline,
        sample_invitations_mixed_statuses,
        updates_captured,
    ):
        client = _build_client(
            sample_bid_package_past_deadline,
            sample_invitations_mixed_statuses,
            updates_captured,
        )

        await expire_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        package_updates = [
            u for u in updates_captured if u["table"] == "bid_packages"
        ]
        assert len(package_updates) >= 1
        assert any(
            u["payload"].get("status") == "closed" for u in package_updates
        )


class TestNoOpWhenDeadlineFuture:
    """If deadline is still in the future, do nothing."""

    @pytest.mark.asyncio
    async def test_noop_future_deadline(
        self,
        sample_bid_package_open,
        sample_invitations_mixed_statuses,
        updates_captured,
    ):
        client = _build_client(
            sample_bid_package_open,
            sample_invitations_mixed_statuses,
            updates_captured,
        )

        result = await expire_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        assert result["expired_count"] == 0
        assert result["package_closed"] is False

        # No writes at all
        assert updates_captured == []


class TestNoOpWhenAlreadyClosed:
    """If bid_package.status is already 'closed', do nothing."""

    @pytest.mark.asyncio
    async def test_noop_already_closed(
        self,
        sample_bid_package_closed,
        sample_invitations_mixed_statuses,
        updates_captured,
    ):
        client = _build_client(
            sample_bid_package_closed,
            sample_invitations_mixed_statuses,
            updates_captured,
        )

        result = await expire_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        assert result["expired_count"] == 0
        assert result["package_closed"] is False
        assert updates_captured == []


class TestNoOpWhenCancelled:
    """If bid_package.status is 'cancelled', do nothing."""

    @pytest.mark.asyncio
    async def test_noop_cancelled(
        self,
        sample_bid_package_cancelled,
        sample_invitations_mixed_statuses,
        updates_captured,
    ):
        client = _build_client(
            sample_bid_package_cancelled,
            sample_invitations_mixed_statuses,
            updates_captured,
        )

        result = await expire_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        assert result["expired_count"] == 0
        assert result["package_closed"] is False
        assert updates_captured == []
