"""Real-DB cancel path: the parent task must not be left stranded.

Cancelling a bid package voided the round and never touched the parent task.
When the cancelled round was the task's only live one, the task stayed in
'bidding' with nothing to bid on: project archive and project delete both 409
naming it, and the "Start New Round" button is gated on task.status === 'draft',
so the PM could not rebid out of it either.

These run against a live Supabase because the defect is a write that does not
happen. The mocked sibling suite asserts on captured update payloads, so an
absent write is invisible to it by construction; that is how this shipped green.

'draft' is the target status because fn_create_bid_package_with_invitations
advances a task only WHERE status = 'draft'. Any other resting value makes a
later rebid a silent no-op.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.services.invitation_tracking_service import (
    InvitationTrackingError,
    cancel_bid_package,
)

pytestmark = pytest.mark.requires_db


# ── Helpers ─────────────────────────────────────────────────────────────


def _task_status(db, task_id: str) -> str:
    return (
        db.table("tasks")
        .select("status")
        .eq("id", task_id)
        .single()
        .execute()
        .data["status"]
    )


def _package(db, package_id: str) -> dict:
    return (
        db.table("bid_packages")
        .select("*")
        .eq("id", package_id)
        .single()
        .execute()
        .data
    )


def _invitation_status(db, invitation_id: str) -> str:
    return (
        db.table("bid_invitations")
        .select("status")
        .eq("id", invitation_id)
        .single()
        .execute()
        .data["status"]
    )


async def _cancel(db, sc, package_id: str | None = None) -> dict:
    return await cancel_bid_package(
        bid_package_id=UUID(package_id or sc.package_id),
        cancelled_by=UUID(sc.admin_user_id),
        db=db,
    )


# ── The task reset ──────────────────────────────────────────────────────


class TestTaskStatusReset:
    """The behaviour this branch adds, and the predicate that bounds it."""

    async def test_last_live_round_returns_task_to_draft(self, db, scenario):
        """One package, cancelled. Nothing left to bid on, so the task reopens."""
        sc = scenario(package_statuses=("open",), task_status="bidding")

        await _cancel(db, sc)

        assert _package(db, sc.package_id)["status"] == "cancelled"
        assert _task_status(db, sc.task_id) == "draft"

    async def test_sibling_live_round_keeps_task_in_bidding(self, db, scenario):
        """Two live rounds, one cancelled. The other is still biddable, so the
        task must stay put. This is the test that fails if the reset is written
        unconditionally.

        Note this state is API-reachable but not UI-reachable: the create-package
        button is gated on task.status === 'draft', which creating the first
        round clears. The guard defends it anyway.
        """
        sc = scenario(package_statuses=("open", "open"), task_status="bidding")

        await _cancel(db, sc, sc.package_ids[0])

        assert _package(db, sc.package_ids[0])["status"] == "cancelled"
        assert _package(db, sc.package_ids[1])["status"] == "open"
        assert _task_status(db, sc.task_id) == "bidding"

    async def test_already_cancelled_sibling_does_not_count_as_live(
        self, db, scenario
    ):
        """A dead round left over from an earlier cancel must not hold the task
        in 'bidding'. Pins that the count filters on status, not on row presence.
        """
        sc = scenario(package_statuses=("cancelled", "open"), task_status="bidding")

        await _cancel(db, sc, sc.package_ids[1])

        assert _task_status(db, sc.task_id) == "draft"

    async def test_evaluating_package_also_resets(self, db, scenario):
        """'evaluating' is cancellable (it is the only escape from a round closed
        early by mistake), so it must reconcile the task the same way 'open' does.
        """
        sc = scenario(package_statuses=("evaluating",), task_status="bidding")

        await _cancel(db, sc)

        assert _task_status(db, sc.task_id) == "draft"

    async def test_non_bidding_task_is_never_stomped(self, db, scenario):
        """A task at 'awarded' with no live award row is the DocuSign-decline
        shape (out of scope to fix here). Cancelling a package underneath it must
        void the round and leave the task exactly where it was: the reset is
        predicated on status = 'bidding' precisely so it cannot clobber this.
        """
        sc = scenario(package_statuses=("open",), task_status="awarded")

        await _cancel(db, sc)

        assert _package(db, sc.package_id)["status"] == "cancelled"
        assert _task_status(db, sc.task_id) == "awarded"


# ── The round trip that was broken ──────────────────────────────────────


class TestCancelThenRebid:
    async def test_rebid_after_cancel_advances_task_and_bumps_round(
        self, db, scenario, parents
    ):
        """The whole point of choosing 'draft': a later rebid flows through
        fn_create_bid_package_with_invitations as designed. Driven through the
        real create RPC, not a raw insert, so the two functions are pinned
        against each other.
        """
        sc = scenario(package_statuses=("open",), task_status="bidding")

        await _cancel(db, sc)
        assert _task_status(db, sc.task_id) == "draft"

        raw = secrets.token_urlsafe(32)
        rpc_result = db.rpc(
            "fn_create_bid_package_with_invitations",
            {
                "p_task_id": sc.task_id,
                "p_deadline": (
                    datetime.now(timezone.utc) + timedelta(days=7)
                ).isoformat(),
                "p_bid_template_id": sc.bid_template_id,
                "p_created_by": sc.admin_user_id,
                "p_instructions": "Round 2 after cancel",
                "p_desired_start_date": None,
                "p_scope_of_work_document_id": None,
                "p_project_document_ids": [],
                "p_vendors": [
                    {
                        "vendor_id": sc.vendor_id,
                        "vendor_contact_id": sc.vendor_contact_id,
                        "token_hash": hashlib.sha256(raw.encode()).hexdigest(),
                    }
                ],
            },
        ).execute()

        result = (
            rpc_result.data[0]
            if isinstance(rpc_result.data, list)
            else rpc_result.data
        )
        new_package_id = result["bid_package_id"]
        sc.tracker.bid_packages.append(new_package_id)
        for row in result.get("invitations") or []:
            # Deleting the invitation cascades its magic_link_tokens row.
            sc.tracker.bid_invitations.append(row["invitation_id"])

        assert result["round_number"] == 2
        assert _package(db, new_package_id)["status"] == "open"
        assert _task_status(db, sc.task_id) == "bidding"


# ── Everything the cancel already did, unchanged ────────────────────────


class TestExistingWritesPreserved:
    async def test_full_cancel_converges_every_row(
        self, db, scenario, add_invitation, add_submission, add_revision_request
    ):
        """One cancel, every side effect asserted from the database.

        Write ORDER stays in the mocked suite, which is the only place a
        sequence of writes is observable; a real DB shows final state only.
        """
        sc = scenario(package_statuses=("open",), task_status="bidding")

        sent = add_invitation(sc, status="sent", with_token=True)
        opened = add_invitation(sc, status="opened")
        declined = add_invitation(sc, status="declined")
        submitted = add_invitation(sc, status="submitted")
        submission = add_submission(sc, submitted)
        revision = add_revision_request(sc, submitted, submission)

        result = await _cancel(db, sc)

        assert result["no_response_count"] == 2
        assert result["revisions_cancelled"] == 1

        # Live invitations converge; terminal ones are left alone.
        assert _invitation_status(db, sent["id"]) == "no_response"
        assert _invitation_status(db, opened["id"]) == "no_response"
        assert _invitation_status(db, declined["id"]) == "declined"
        assert _invitation_status(db, submitted["id"]) == "submitted"

        # The pending revision is cancelled and its token hard-revoked: a
        # revision token is gated by its own deadline, not the package status,
        # so it would otherwise outlive the round.
        revision_row = (
            db.table("bid_revision_requests")
            .select("status")
            .eq("id", revision["id"])
            .single()
            .execute()
            .data
        )
        assert revision_row["status"] == "cancelled"

        revision_token = (
            db.table("magic_link_tokens")
            .select("is_used, revoked_at, revoked_by")
            .eq("id", revision["token_id"])
            .single()
            .execute()
            .data
        )
        assert revision_token["is_used"] is True
        assert revision_token["revoked_at"] is not None
        assert revision_token["revoked_by"] == sc.admin_user_id

        # Submitted bids are preserved as history, never deleted.
        assert (
            db.table("bid_submissions")
            .select("id")
            .eq("id", submission["id"])
            .single()
            .execute()
            .data["id"]
            == submission["id"]
        )

        package = _package(db, sc.package_id)
        assert package["status"] == "cancelled"
        assert package["cancelled_by"] == sc.admin_user_id
        assert package["cancelled_at"] is not None
        assert _task_status(db, sc.task_id) == "draft"

    async def test_initial_bid_tokens_are_not_revoked(
        self, db, scenario, add_invitation
    ):
        """Only REVISION tokens are revoked. An ordinary bid token stays live in
        the table; the vendor is locked out by the package-status gate in
        vendor_auth (423), not by token revocation. Pinning the current
        behaviour so the RPC swap cannot quietly change it.
        """
        sc = scenario(package_statuses=("open",), task_status="bidding")
        invitation = add_invitation(sc, status="sent", with_token=True)

        await _cancel(db, sc)

        token = (
            db.table("magic_link_tokens")
            .select("revoked_at")
            .eq("id", invitation["token_id"])
            .single()
            .execute()
            .data
        )
        assert token["revoked_at"] is None


# ── Guards, unchanged ───────────────────────────────────────────────────


class TestGuardsUnchanged:
    async def test_unknown_package_is_404(self, db, scenario):
        sc = scenario()

        with pytest.raises(InvitationTrackingError) as ei:
            await _cancel(db, sc, str(uuid4()))

        assert ei.value.status_code == 404

    @pytest.mark.parametrize("blocked_status", ["cancelled", "closed"])
    async def test_non_cancellable_status_is_409(self, db, scenario, blocked_status):
        """Re-cancelling is 409, and so is 'closed'. The task is untouched."""
        sc = scenario(package_statuses=(blocked_status,), task_status="bidding")

        with pytest.raises(InvitationTrackingError) as ei:
            await _cancel(db, sc)

        assert ei.value.status_code == 409
        assert blocked_status in str(ei.value.detail)
        assert _task_status(db, sc.task_id) == "bidding"

    async def test_awarded_task_is_409_and_writes_nothing(
        self, db, scenario, add_invitation, add_submission, add_award
    ):
        """A live award owns an award -> contract -> milestones chain; voiding
        the round underneath it would orphan that chain.
        """
        sc = scenario(package_statuses=("open",), task_status="bidding")
        invitation = add_invitation(sc, status="submitted")
        submission = add_submission(sc, invitation)
        add_award(sc, submission, status="pending_acceptance")

        with pytest.raises(InvitationTrackingError) as ei:
            await _cancel(db, sc)

        assert ei.value.status_code == 409
        assert "awarded" in str(ei.value.detail).lower()
        assert _package(db, sc.package_id)["status"] == "open"
        assert _invitation_status(db, invitation["id"]) == "submitted"
        assert _task_status(db, sc.task_id) == "bidding"
