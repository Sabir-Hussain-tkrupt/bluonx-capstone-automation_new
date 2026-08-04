"""
Cancel bid package service path (open | evaluating -> cancelled).

Voiding a round must:
  - be reachable from 'evaluating', not just 'open' — nothing reopens a package,
    so this is the only escape from a round closed early by mistake;
  - refuse when the task already has a live award (that would orphan the
    award -> contract -> milestones chain);
  - cancel every PENDING revision request. Ordinary bid access dies with the
    status flip, but a revision token is validated against its own status and
    deadline, explicitly NOT the package status, so it survives otherwise;
  - converge sent/opened to no_response (the deadline sweep skips cancelled
    packages, so rows left live would stay stale forever);
  - preserve submitted bids — cancelling makes them unawardable, not deleted;
  - stamp cancelled_by / cancelled_at.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.invitation_tracking_service import (
    InvitationTrackingError,
    cancel_bid_package,
)

PKG = str(uuid4())
TASK = str(uuid4())
USER = uuid4()


def _make_db(
    package: dict,
    captured: list,
    invitations: list | None = None,
    awards: list | None = None,
):
    """Mock supabase client. Captures every update payload with its table so
    ordering and targeting can be asserted."""
    client = MagicMock()

    def _table(name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.single.return_value = chain
        chain.limit.return_value = chain
        chain.in_.return_value = chain
        chain.order.return_value = chain

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
            elif name == "awards":
                res.data = list(awards or [])
            else:
                res.data = []
            return res

        chain.execute.side_effect = _execute
        return chain

    client.table.side_effect = _table
    return client


def _inv(status: str) -> dict:
    return {"id": str(uuid4()), "status": status}


def _pkg(status: str = "open") -> dict:
    return {"id": PKG, "status": status, "task_id": TASK}


def _updates_for(captured: list, table: str) -> list[dict]:
    return [c["payload"] for c in captured if c["table"] == table]


@pytest.fixture()
def no_revisions(monkeypatch):
    """Default: the package has no revision requests."""
    monkeypatch.setattr(
        "app.services.invitation_tracking_service.list_revision_requests_for_package",
        lambda db, *, bid_package_id: [],
    )


class TestAllowedStatuses:
    async def test_cancels_from_open(self, no_revisions):
        captured: list = []
        db = _make_db(_pkg("open"), captured)

        result = await cancel_bid_package(
            bid_package_id=PKG, cancelled_by=USER, db=db
        )

        assert result["status"] == "cancelled"
        assert _updates_for(captured, "bid_packages")[0]["status"] == "cancelled"

    async def test_cancels_from_evaluating(self, no_revisions):
        """The escape hatch for a round closed early by mistake."""
        captured: list = []
        db = _make_db(_pkg("evaluating"), captured)

        result = await cancel_bid_package(
            bid_package_id=PKG, cancelled_by=USER, db=db
        )

        assert result["status"] == "cancelled"

    @pytest.mark.parametrize("status", ["closed", "cancelled"])
    async def test_rejects_other_statuses_409(self, status, no_revisions):
        captured: list = []
        db = _make_db(_pkg(status), captured)

        with pytest.raises(InvitationTrackingError) as ei:
            await cancel_bid_package(bid_package_id=PKG, cancelled_by=USER, db=db)

        assert ei.value.status_code == 409
        assert captured == []

    async def test_unknown_package_404(self, no_revisions):
        captured: list = []
        db = _make_db(None, captured)

        with pytest.raises(InvitationTrackingError) as ei:
            await cancel_bid_package(bid_package_id=PKG, cancelled_by=USER, db=db)

        assert ei.value.status_code == 404


class TestAwardGuard:
    async def test_rejects_when_task_already_awarded(self, no_revisions):
        captured: list = []
        db = _make_db(
            _pkg("evaluating"),
            captured,
            awards=[{"id": str(uuid4()), "status": "accepted",
                     "bid_submission_id": str(uuid4())}],
        )

        with pytest.raises(InvitationTrackingError) as ei:
            await cancel_bid_package(bid_package_id=PKG, cancelled_by=USER, db=db)

        assert ei.value.status_code == 409
        assert "awarded" in str(ei.value.detail).lower()
        # The guard must fire before anything is written.
        assert captured == []

    async def test_allows_when_award_is_not_blocking(self, no_revisions):
        """A declined/cancelled award leaves the task re-awardable, so the round
        can still be voided."""
        captured: list = []
        db = _make_db(
            _pkg("open"),
            captured,
            awards=[{"id": str(uuid4()), "status": "declined_by_vendor",
                     "bid_submission_id": str(uuid4())}],
        )

        result = await cancel_bid_package(
            bid_package_id=PKG, cancelled_by=USER, db=db
        )

        assert result["status"] == "cancelled"


class TestPendingRevisionsAreCancelled:
    """A revision token outlives the package status flip, so it must be
    explicitly cancelled or the vendor can still submit into a void round."""

    def _stub_revisions(self, monkeypatch, statuses: list[str]) -> list:
        cancelled: list = []
        revisions = [
            SimpleNamespace(id=str(uuid4()), status=s) for s in statuses
        ]
        monkeypatch.setattr(
            "app.services.invitation_tracking_service.list_revision_requests_for_package",
            lambda db, *, bid_package_id: revisions,
        )
        monkeypatch.setattr(
            "app.services.invitation_tracking_service.cancel_revision_request",
            lambda db, *, revision_request_id, cancelled_by: cancelled.append(
                revision_request_id
            ),
        )
        return cancelled

    async def test_cancels_every_pending_request(self, monkeypatch):
        cancelled = self._stub_revisions(monkeypatch, ["pending", "pending"])
        db = _make_db(_pkg("open"), [])

        result = await cancel_bid_package(
            bid_package_id=PKG, cancelled_by=USER, db=db
        )

        assert result["revisions_cancelled"] == 2
        assert len(cancelled) == 2

    @pytest.mark.parametrize(
        "status", ["submitted", "declined", "expired", "cancelled"]
    )
    async def test_leaves_non_pending_requests_alone(self, monkeypatch, status):
        cancelled = self._stub_revisions(monkeypatch, [status])
        db = _make_db(_pkg("open"), [])

        result = await cancel_bid_package(
            bid_package_id=PKG, cancelled_by=USER, db=db
        )

        assert result["revisions_cancelled"] == 0
        assert cancelled == []

    async def test_mixed_cohort_cancels_only_pending(self, monkeypatch):
        cancelled = self._stub_revisions(
            monkeypatch, ["pending", "submitted", "pending", "declined"]
        )
        db = _make_db(_pkg("open"), [])

        result = await cancel_bid_package(
            bid_package_id=PKG, cancelled_by=USER, db=db
        )

        assert result["revisions_cancelled"] == 2
        assert len(cancelled) == 2


class TestInvitationConvergence:
    async def test_sent_and_opened_become_no_response(self, no_revisions):
        captured: list = []
        db = _make_db(
            _pkg("open"),
            captured,
            invitations=[_inv("sent"), _inv("opened")],
        )

        result = await cancel_bid_package(
            bid_package_id=PKG, cancelled_by=USER, db=db
        )

        assert result["no_response_count"] == 2
        inv_updates = _updates_for(captured, "bid_invitations")
        assert len(inv_updates) == 1
        assert inv_updates[0]["status"] == "no_response"

    @pytest.mark.parametrize(
        "status", ["submitted", "declined", "no_response", "pending_send", "send_failed"]
    )
    async def test_other_statuses_untouched(self, status, no_revisions):
        """A submitted bid must survive: cancelling makes it unawardable, it
        does not erase the round's history."""
        captured: list = []
        db = _make_db(_pkg("open"), captured, invitations=[_inv(status)])

        result = await cancel_bid_package(
            bid_package_id=PKG, cancelled_by=USER, db=db
        )

        assert result["no_response_count"] == 0
        assert _updates_for(captured, "bid_invitations") == []


class TestAttributionAndOrdering:
    async def test_stamps_cancelled_by_and_at(self, no_revisions):
        captured: list = []
        db = _make_db(_pkg("open"), captured)

        await cancel_bid_package(bid_package_id=PKG, cancelled_by=USER, db=db)

        payload = _updates_for(captured, "bid_packages")[0]
        assert payload["cancelled_by"] == str(USER)
        assert payload["cancelled_at"]
        # cancelled_at and updated_at share one timestamp.
        assert payload["cancelled_at"] == payload["updated_at"]

    async def test_invitations_converge_before_package_flip(self, no_revisions):
        """The flip goes last so a mid-way failure leaves a still-open package
        the deadline sweep reconciles, never a cancelled package with live
        vendor access."""
        captured: list = []
        db = _make_db(_pkg("open"), captured, invitations=[_inv("sent")])

        await cancel_bid_package(bid_package_id=PKG, cancelled_by=USER, db=db)

        tables = [c["table"] for c in captured]
        assert tables.index("bid_invitations") < tables.index("bid_packages")
