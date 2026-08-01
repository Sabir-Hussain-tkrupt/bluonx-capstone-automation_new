"""
Tests for the sweep_overdue_invitations() lazy read-path entry point and the
shared _apply_overdue_transition() core.

Given a bid_package_id, if the deadline has passed and the package is not
terminal (closed/cancelled), it flips all 'sent'/'opened' invitations to
'no_response' (the single terminal "invited, no bid by the deadline" status) and
moves an 'open' package to 'evaluating'. It never touches 'submitted' or
'declined' rows, and is a no-op (no writes) when the deadline hasn't passed or
the package is already 'closed'/'cancelled'.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.invitation_tracking_service import sweep_overdue_invitations

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

        def capture(payload, _chain=chain, _name=name):
            updates_captured.append({"table": _name, "payload": payload})
            return _chain

        chain.update.side_effect = capture
        return chain

    client.table.side_effect = table_side_effect
    return client


class TestOverdueBecomeNoResponse:
    """sent/opened invitations become no_response when the deadline has passed."""

    @pytest.mark.asyncio
    async def test_sent_and_opened_become_no_response(
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

        result = await sweep_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        assert result["no_response_count"] == 2  # 'sent' + 'opened'
        assert result["package_moved"] is True

        # At least one bid_invitations update with status='no_response'
        invitation_updates = [
            u for u in updates_captured
            if u["table"] == "bid_invitations"
            and u["payload"].get("status") == "no_response"
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

        await sweep_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        # The update payload for bid_invitations should only ever be
        # status='no_response' — never 'submitted' or 'declined'.
        invitation_update_payloads = [
            u["payload"] for u in updates_captured
            if u["table"] == "bid_invitations"
        ]
        for payload in invitation_update_payloads:
            status = payload.get("status")
            if status is not None:
                assert status == "no_response"


class TestUpdatesBidPackageToEvaluating:
    """bid_packages.status flips from 'open' to 'evaluating' (the sweep never
    writes 'closed'; that is reserved for award acceptance)."""

    @pytest.mark.asyncio
    async def test_package_status_evaluating(
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

        await sweep_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        package_updates = [
            u for u in updates_captured if u["table"] == "bid_packages"
        ]
        assert len(package_updates) >= 1
        assert any(
            u["payload"].get("status") == "evaluating" for u in package_updates
        )
        assert not any(
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

        result = await sweep_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        assert result["no_response_count"] == 0
        assert result["package_moved"] is False

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

        result = await sweep_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        assert result["no_response_count"] == 0
        assert result["package_moved"] is False
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

        result = await sweep_overdue_invitations(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        assert result["no_response_count"] == 0
        assert result["package_moved"] is False
        assert updates_captured == []
