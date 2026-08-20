"""
Manual "close bidding early" service path (open -> evaluating).

close_bidding is the PM action; it must move an OPEN package to 'evaluating'
(before or after deadline) and reject any non-open package with 409.

It must also converge invitations exactly as the deadline transition does:
every 'sent'/'opened' row becomes 'no_response'. Without that, an early close
leaves rows reading 'sent' until the original deadline passes even though
nobody can bid — and the UI keeps offering Resend / Mark Declined on them.
No token revocation: the status flip alone locks vendors out.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.invitation_tracking_service import (
    InvitationTrackingError,
    close_bidding,
)

PKG = str(uuid4())


def _make_db(package: dict, captured: list, invitations: list | None = None) -> MagicMock:
    """Mock supabase client: bid_packages select->single->execute returns
    `package`, bid_invitations returns `invitations`; update payloads are
    captured with the table they targeted."""
    client = MagicMock()

    def _table(name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.single.return_value = chain
        chain.maybe_single.return_value = chain
        chain.limit.return_value = chain
        chain.in_.return_value = chain

        def _update(payload):
            captured.append({"table": name, "payload": payload})
            return chain

        chain.update.side_effect = _update

        def _execute():
            res = MagicMock()
            if name == "bid_packages":
                res.data = package
            elif name == "bid_invitations":
                res.data = list(invitations or [])
            else:
                res.data = []
            return res

        chain.execute.side_effect = _execute
        return chain

    client.table.side_effect = _table
    return client


def _inv(status: str) -> dict:
    return {"id": str(uuid4()), "status": status}


def _updates_for(captured: list, table: str) -> list[dict]:
    return [c["payload"] for c in captured if c["table"] == table]


async def test_close_open_moves_to_evaluating():
    captured: list = []
    db = _make_db({"id": PKG, "status": "open"}, captured)
    result = await close_bidding(bid_package_id=PKG, db=db)
    assert result == {"id": PKG, "status": "evaluating", "no_response_count": 0}
    pkg_updates = _updates_for(captured, "bid_packages")
    assert pkg_updates and pkg_updates[0]["status"] == "evaluating"


@pytest.mark.parametrize("status", ["evaluating", "closed", "cancelled"])
async def test_close_rejects_non_open_409(status):
    captured: list = []
    db = _make_db({"id": PKG, "status": status}, captured)
    with pytest.raises(InvitationTrackingError) as ei:
        await close_bidding(bid_package_id=PKG, db=db)
    assert ei.value.status_code == 409
    # No write happened — the guard fired before any update.
    assert captured == []


class TestInvitationConvergence:
    """Early close must leave the same invitation state as a passed deadline."""

    async def test_sent_and_opened_flip_to_no_response(self):
        captured: list = []
        db = _make_db(
            {"id": PKG, "status": "open"},
            captured,
            invitations=[_inv("sent"), _inv("opened"), _inv("sent")],
        )
        result = await close_bidding(bid_package_id=PKG, db=db)

        assert result["no_response_count"] == 3
        inv_updates = _updates_for(captured, "bid_invitations")
        assert len(inv_updates) == 1
        assert inv_updates[0]["status"] == "no_response"

    @pytest.mark.parametrize(
        "status", ["submitted", "declined", "no_response", "pending_send", "send_failed"]
    )
    async def test_other_statuses_are_left_alone(self, status):
        """Only the two live statuses convert. A submitted bid in particular must
        survive untouched — it is still awardable from 'evaluating'."""
        captured: list = []
        db = _make_db({"id": PKG, "status": "open"}, captured, invitations=[_inv(status)])
        result = await close_bidding(bid_package_id=PKG, db=db)

        assert result["no_response_count"] == 0
        assert _updates_for(captured, "bid_invitations") == []

    async def test_mixed_cohort_counts_only_live_rows(self):
        captured: list = []
        db = _make_db(
            {"id": PKG, "status": "open"},
            captured,
            invitations=[_inv("sent"), _inv("submitted"), _inv("opened"), _inv("declined")],
        )
        result = await close_bidding(bid_package_id=PKG, db=db)

        assert result["no_response_count"] == 2
        # The package still advances regardless of how many rows converged.
        assert _updates_for(captured, "bid_packages")[0]["status"] == "evaluating"

    async def test_no_live_invitations_writes_nothing_to_invitations(self):
        """Idempotence guard: nothing live means no invitation write at all."""
        captured: list = []
        db = _make_db({"id": PKG, "status": "open"}, captured, invitations=[])
        result = await close_bidding(bid_package_id=PKG, db=db)

        assert result["no_response_count"] == 0
        assert _updates_for(captured, "bid_invitations") == []
        assert _updates_for(captured, "bid_packages")[0]["status"] == "evaluating"

    async def test_invitations_converge_before_package_moves(self):
        """Ordering matters: the invitation flip selects on the package id, not
        its status, but converging first keeps the two writes consistent if the
        package update fails."""
        captured: list = []
        db = _make_db(
            {"id": PKG, "status": "open"}, captured, invitations=[_inv("sent")]
        )
        await close_bidding(bid_package_id=PKG, db=db)

        tables = [c["table"] for c in captured]
        assert tables.index("bid_invitations") < tables.index("bid_packages")
