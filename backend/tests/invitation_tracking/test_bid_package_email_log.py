"""Tests for GET /v1/bid-packages/{bid_package_id}/email-log.

The service reads v_vendor_email_log filtered on bid_package_id. The view
carries that column only for the three invitation-linked flows
(bid_invitations, bid_revision_requests, bid_submissions); award and milestone
rows have a NULL bid_package_id and so are scoped out here by construction,
leaving the package log's contents exactly as they were before pagination.

The union and the sort now happen in Postgres, so these tests seed view rows
and assert the service's contract: the (items, total) pair, correct slicing,
newest-first ordering, package scoping, and the 404 guard.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.services.invitation_tracking_service import (
    BidPackageNotFoundError,
    get_bid_package_email_log,
)
from tests._fakes import FakeRowsSupabase


VIEW = "v_vendor_email_log"
BASE = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _db() -> FakeRowsSupabase:
    return FakeRowsSupabase({"bid_packages": [], VIEW: []})


def _seed_package(db: FakeRowsSupabase, package_id: UUID) -> None:
    db.tables["bid_packages"].append(
        {
            "id": str(package_id),
            "task_id": str(uuid4()),
            "round_number": 1,
            "status": "open",
            "tasks": {"name": "T"},
            "bid_templates": {"id": str(uuid4()), "name": "Tpl", "is_lump_sum": True},
        }
    )


def _seed_email(
    db: FakeRowsSupabase,
    package_id: UUID | None,
    *,
    email_id: UUID | None = None,
    reference_type: str = "bid_invitations",
    email_type: str = "general",
    status: str = "sent",
    error_message: str | None = None,
    minutes_ago: int = 0,
) -> UUID:
    """Append one v_vendor_email_log row. Larger minutes_ago = older."""
    email_id = email_id or uuid4()
    created = BASE - timedelta(minutes=minutes_ago)
    db.tables.setdefault(VIEW, []).append(
        {
            "id": str(email_id),
            "recipient_email": "v@example.com",
            "recipient_type": "vendor_contact",
            "email_type": email_type,
            "subject": "subj",
            "reference_type": reference_type,
            "reference_id": str(uuid4()),
            "status": status,
            "sent_at": None if status == "failed" else created.isoformat(),
            "opened_at": None,
            "clicked_at": None,
            "error_message": error_message,
            "retry_count": 0,
            "created_at": created.isoformat(),
            "vendor_id": str(uuid4()),
            "bid_invitation_id": str(uuid4()),
            "bid_package_id": None if package_id is None else str(package_id),
        }
    )
    return email_id


class TestReturnsRowsForThePackage:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self):
        db = _db()
        pkg_id = uuid4()
        _seed_package(db, pkg_id)
        for i in range(3):
            _seed_email(db, pkg_id, minutes_ago=i)

        items, total = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        assert total == 3
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_unions_the_three_invitation_linked_flows(self):
        db = _db()
        pkg_id = uuid4()
        _seed_package(db, pkg_id)
        _seed_email(db, pkg_id, reference_type="bid_invitations",
                    email_type="bid_invitation", minutes_ago=4)
        _seed_email(db, pkg_id, reference_type="bid_invitations",
                    email_type="bid_reminder", minutes_ago=3)
        _seed_email(db, pkg_id, reference_type="bid_revision_requests", minutes_ago=2)
        _seed_email(db, pkg_id, reference_type="bid_submissions", minutes_ago=1)
        _seed_email(db, pkg_id, reference_type="bid_submissions", minutes_ago=0)

        items, total = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        assert total == 5
        assert {i["reference_type"] for i in items} == {
            "bid_invitations",
            "bid_revision_requests",
            "bid_submissions",
        }

    @pytest.mark.asyncio
    async def test_excludes_emails_from_other_packages(self):
        db = _db()
        pkg_id, other_pkg = uuid4(), uuid4()
        _seed_package(db, pkg_id)
        ours = _seed_email(db, pkg_id)
        _seed_email(db, other_pkg)

        items, total = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        assert total == 1
        assert [i["id"] for i in items] == [str(ours)]

    @pytest.mark.asyncio
    async def test_excludes_rows_with_no_package(self):
        # Award and milestone rows carry a NULL bid_package_id, which is what
        # keeps the package log unchanged now that the vendor log is wider.
        db = _db()
        pkg_id = uuid4()
        _seed_package(db, pkg_id)
        _seed_email(db, None, reference_type="awards")
        _seed_email(db, None, reference_type="milestones")

        items, total = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        assert (items, total) == ([], 0)


class TestRowShape:
    @pytest.mark.asyncio
    async def test_row_has_the_fields_the_ui_needs(self):
        db = _db()
        pkg_id = uuid4()
        _seed_package(db, pkg_id)
        _seed_email(db, pkg_id)

        items, _ = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        for field in (
            "recipient_email", "email_type", "subject",
            "status", "sent_at", "error_message",
        ):
            assert field in items[0]

    @pytest.mark.asyncio
    async def test_failed_row_carries_its_error(self):
        db = _db()
        pkg_id = uuid4()
        _seed_package(db, pkg_id)
        _seed_email(db, pkg_id, status="failed",
                    error_message="SMTP 550: mailbox not found")

        items, _ = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        assert items[0]["error_message"] == "SMTP 550: mailbox not found"
        assert items[0]["sent_at"] is None


class TestOrderingAndPaging:
    @pytest.mark.asyncio
    async def test_sorted_newest_first(self):
        db = _db()
        pkg_id = uuid4()
        _seed_package(db, pkg_id)
        oldest = _seed_email(db, pkg_id, minutes_ago=180)
        newest = _seed_email(db, pkg_id, minutes_ago=0)
        middle = _seed_email(db, pkg_id, minutes_ago=60)

        items, _ = await get_bid_package_email_log(bid_package_id=pkg_id, db=db)

        assert [i["id"] for i in items] == [str(newest), str(middle), str(oldest)]

    @pytest.mark.asyncio
    async def test_pages_through_without_repeating_rows(self):
        db = _db()
        pkg_id = uuid4()
        _seed_package(db, pkg_id)
        for i in range(5):
            _seed_email(db, pkg_id, minutes_ago=i)

        first, total = await get_bid_package_email_log(
            bid_package_id=pkg_id, db=db, page=1, page_size=2
        )
        second, _ = await get_bid_package_email_log(
            bid_package_id=pkg_id, db=db, page=2, page_size=2
        )

        assert total == 5
        assert len(first) == len(second) == 2
        assert {i["id"] for i in first}.isdisjoint({i["id"] for i in second})

    @pytest.mark.asyncio
    async def test_page_past_the_end_is_empty_with_the_true_total(self):
        db = _db()
        pkg_id = uuid4()
        _seed_package(db, pkg_id)
        _seed_email(db, pkg_id)

        items, total = await get_bid_package_email_log(
            bid_package_id=pkg_id, db=db, page=9, page_size=25
        )

        assert items == []
        assert total == 1


class TestEmptyEmailLog:
    @pytest.mark.asyncio
    async def test_empty_pair(self):
        db = _db()
        pkg_id = uuid4()
        _seed_package(db, pkg_id)

        assert await get_bid_package_email_log(bid_package_id=pkg_id, db=db) == ([], 0)


class TestNonexistentBidPackage:
    @pytest.mark.asyncio
    async def test_raises_not_found(self):
        with pytest.raises(BidPackageNotFoundError):
            await get_bid_package_email_log(bid_package_id=uuid4(), db=_db())
