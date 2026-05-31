"""
Tests for GET /v1/bid-packages/{bid_package_id}/email-log.

Returns all email_log rows where reference_type='bid_invitations' and
reference_id matches an invitation in this bid package.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Import will fail until implementation lands — expected for test-first.
from app.services.invitation_tracking_service import (
    BidPackageNotFoundError,
    get_bid_package_email_log,
)

from .conftest import (
    BID_PACKAGE_ID,
    NONEXISTENT_BID_PACKAGE_ID,
    build_chain,
)


class TestReturnsRowsForInvitations:
    """Service returns every email_log row whose reference_id matches an
    invitation in the package."""

    @pytest.mark.asyncio
    async def test_returns_all_logged_emails(self, mock_supabase):
        result = await get_bid_package_email_log(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        assert isinstance(result, list)
        assert len(result) == 3


class TestRowShape:
    """Each row exposes the fields the PM UI needs."""

    @pytest.mark.asyncio
    async def test_row_has_expected_fields(self, mock_supabase):
        result = await get_bid_package_email_log(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        for row in result:
            assert "recipient_email" in row
            assert "email_type" in row
            assert "subject" in row
            assert "status" in row
            assert "sent_at" in row
            assert "error_message" in row

    @pytest.mark.asyncio
    async def test_failed_row_contains_error_message(self, mock_supabase):
        result = await get_bid_package_email_log(
            bid_package_id=BID_PACKAGE_ID,
            db=mock_supabase,
        )

        failed = [r for r in result if r["status"] == "failed"]
        assert len(failed) == 1
        assert failed[0]["error_message"] == "SMTP 550: mailbox not found"
        assert failed[0]["sent_at"] is None


class TestEmptyEmailLog:
    """When no emails have been logged, returns []."""

    @pytest.mark.asyncio
    async def test_empty_array(
        self,
        sample_bid_package_open,
        sample_invitations_mixed_statuses,
    ):
        client = MagicMock()

        def table_side_effect(name):
            if name == "bid_packages":
                return build_chain(data=[sample_bid_package_open])
            if name == "bid_invitations":
                return build_chain(data=sample_invitations_mixed_statuses)
            if name == "email_log":
                return build_chain(data=[])
            return build_chain(data=[])

        client.table.side_effect = table_side_effect

        result = await get_bid_package_email_log(
            bid_package_id=BID_PACKAGE_ID,
            db=client,
        )

        assert result == []


class TestNonexistentBidPackage:
    """404 when bid_package_id doesn't exist."""

    @pytest.mark.asyncio
    async def test_raises_not_found(self):
        client = MagicMock()

        def table_side_effect(name):
            return build_chain(data=[])

        client.table.side_effect = table_side_effect

        with pytest.raises(BidPackageNotFoundError):
            await get_bid_package_email_log(
                bid_package_id=NONEXISTENT_BID_PACKAGE_ID,
                db=client,
            )


# ── Filter-aware fake (for broadened-filter regression) ────────────────────
#
# The shared mock_supabase in conftest ignores .eq() / .in_() entirely, so
# every email_log query would return the same seeded rows — useless for
# verifying the new union-by-reference_type behavior. This local fake
# captures .eq(col, val) and .in_(col, vals) and applies them to the
# table's data on .execute(), so seeded rows route to the right branch.


from datetime import datetime, timedelta, timezone
from uuid import uuid4


class _Chain:
    def __init__(self, rows: list[dict]):
        self._rows = list(rows)
        self._filters: list[tuple] = []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        out = self._rows
        for kind, col, val in self._filters:
            if kind == "eq":
                out = [r for r in out if str(r.get(col)) == str(val)]
            elif kind == "in":
                wanted = {str(v) for v in val}
                out = [r for r in out if str(r.get(col)) in wanted]
        result = type("R", (), {})()
        result.data = out[0] if getattr(self, "_single", False) else out
        return result


class _FilterAwareDB:
    """Per-table row store + per-call _Chain. Respects .eq / .in_."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "bid_packages": [],
            "bid_invitations": [],
            "bid_revision_requests": [],
            "bid_submissions": [],
            "email_log": [],
        }

    def table(self, name: str) -> _Chain:
        return _Chain(self.tables.get(name, []))


def _seed_package(db: _FilterAwareDB, package_id, task_id):
    db.tables["bid_packages"].append(
        {
            "id": str(package_id),
            "task_id": str(task_id),
            "round_number": 1,
            "status": "open",
            "tasks": {"name": "T"},
            "bid_templates": {"id": str(uuid4()), "name": "Tpl", "is_lump_sum": True},
        }
    )


def _seed_invitation(db: _FilterAwareDB, invitation_id, package_id):
    db.tables["bid_invitations"].append(
        {"id": str(invitation_id), "bid_package_id": str(package_id)}
    )


def _seed_email(
    db: _FilterAwareDB,
    *,
    email_id,
    reference_type: str,
    reference_id,
    email_type: str = "general",
    created_at: datetime | None = None,
    subject: str = "subj",
):
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    db.tables["email_log"].append(
        {
            "id": str(email_id),
            "recipient_email": "v@example.com",
            "recipient_type": "vendor_contact",
            "email_type": email_type,
            "subject": subject,
            "reference_type": reference_type,
            "reference_id": str(reference_id),
            "status": "sent",
            "sent_at": created_at.isoformat(),
            "error_message": None,
            "created_at": created_at.isoformat(),
        }
    )


class TestBroadenedFilter:
    """The endpoint must return email_log rows for ALL three reference_types
    that downstream flows write today, not just bid_invitations."""

    @pytest.mark.asyncio
    async def test_includes_revision_request_emails(self):
        db = _FilterAwareDB()
        pkg_id, task_id, inv_id, rr_id, email_id = (uuid4() for _ in range(5))
        _seed_package(db, pkg_id, task_id)
        _seed_invitation(db, inv_id, pkg_id)
        db.tables["bid_revision_requests"].append(
            {"id": str(rr_id), "bid_invitation_id": str(inv_id)}
        )
        _seed_email(
            db,
            email_id=email_id,
            reference_type="bid_revision_requests",
            reference_id=rr_id,
        )

        result = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        assert len(result) == 1
        assert result[0]["id"] == str(email_id)
        assert result[0]["reference_type"] == "bid_revision_requests"

    @pytest.mark.asyncio
    async def test_includes_initial_submission_emails(self):
        db = _FilterAwareDB()
        pkg_id, task_id, inv_id, sub_id, email_id = (uuid4() for _ in range(5))
        _seed_package(db, pkg_id, task_id)
        _seed_invitation(db, inv_id, pkg_id)
        db.tables["bid_submissions"].append(
            {"id": str(sub_id), "bid_invitation_id": str(inv_id)}
        )
        _seed_email(
            db,
            email_id=email_id,
            reference_type="bid_submissions",
            reference_id=sub_id,
        )

        result = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        assert len(result) == 1
        assert result[0]["id"] == str(email_id)

    @pytest.mark.asyncio
    async def test_includes_all_four_flows_unioned(self):
        """Initial invitation + reminder + revision request + initial bid
        receipt + revision receipt = 5 rows."""
        db = _FilterAwareDB()
        pkg_id, task_id, inv_id = uuid4(), uuid4(), uuid4()
        rr_id, sub1_id, sub2_id = uuid4(), uuid4(), uuid4()
        ids = [uuid4() for _ in range(5)]
        _seed_package(db, pkg_id, task_id)
        _seed_invitation(db, inv_id, pkg_id)
        db.tables["bid_revision_requests"].append(
            {"id": str(rr_id), "bid_invitation_id": str(inv_id)}
        )
        db.tables["bid_submissions"].extend(
            [
                {"id": str(sub1_id), "bid_invitation_id": str(inv_id)},
                {"id": str(sub2_id), "bid_invitation_id": str(inv_id)},
            ]
        )
        _seed_email(db, email_id=ids[0], reference_type="bid_invitations",
                    reference_id=inv_id, email_type="bid_invitation")
        _seed_email(db, email_id=ids[1], reference_type="bid_invitations",
                    reference_id=inv_id, email_type="bid_reminder")
        _seed_email(db, email_id=ids[2], reference_type="bid_revision_requests",
                    reference_id=rr_id)
        _seed_email(db, email_id=ids[3], reference_type="bid_submissions",
                    reference_id=sub1_id)
        _seed_email(db, email_id=ids[4], reference_type="bid_submissions",
                    reference_id=sub2_id)

        result = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        assert len(result) == 5
        returned_ids = {r["id"] for r in result}
        assert returned_ids == {str(i) for i in ids}

    @pytest.mark.asyncio
    async def test_sorted_by_created_at_desc(self):
        db = _FilterAwareDB()
        pkg_id, task_id, inv_id = uuid4(), uuid4(), uuid4()
        rr_id, sub_id = uuid4(), uuid4()
        _seed_package(db, pkg_id, task_id)
        _seed_invitation(db, inv_id, pkg_id)
        db.tables["bid_revision_requests"].append(
            {"id": str(rr_id), "bid_invitation_id": str(inv_id)}
        )
        db.tables["bid_submissions"].append(
            {"id": str(sub_id), "bid_invitation_id": str(inv_id)}
        )
        base = datetime.now(timezone.utc)
        oldest = uuid4()
        middle = uuid4()
        newest = uuid4()
        _seed_email(db, email_id=oldest, reference_type="bid_invitations",
                    reference_id=inv_id, created_at=base - timedelta(hours=3))
        _seed_email(db, email_id=newest, reference_type="bid_submissions",
                    reference_id=sub_id, created_at=base)
        _seed_email(db, email_id=middle, reference_type="bid_revision_requests",
                    reference_id=rr_id, created_at=base - timedelta(hours=1))

        result = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        assert [r["id"] for r in result] == [str(newest), str(middle), str(oldest)]

    @pytest.mark.asyncio
    async def test_excludes_emails_from_other_packages(self):
        """An email tied to a different bid_package's invitation must not leak."""
        db = _FilterAwareDB()
        pkg_id, task_id, our_inv = uuid4(), uuid4(), uuid4()
        other_inv = uuid4()
        ours_email, other_email = uuid4(), uuid4()
        _seed_package(db, pkg_id, task_id)
        _seed_invitation(db, our_inv, pkg_id)
        # other_inv belongs to a different package — NOT seeded into bid_packages
        db.tables["bid_invitations"].append(
            {"id": str(other_inv), "bid_package_id": str(uuid4())}
        )
        _seed_email(db, email_id=ours_email, reference_type="bid_invitations",
                    reference_id=our_inv)
        _seed_email(db, email_id=other_email, reference_type="bid_invitations",
                    reference_id=other_inv)

        result = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        returned_ids = {r["id"] for r in result}
        assert returned_ids == {str(ours_email)}
