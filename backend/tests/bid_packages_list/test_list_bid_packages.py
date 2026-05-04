"""
Tests for `list_bid_packages` service (Task 6.2).

Covers the cross-project bid package list view: denormalized project /
task names, SQL-computed invitation counts, status / project filters,
sort options, and validation of bad query params.
"""

from __future__ import annotations

import pytest

# Import will fail until the service module is created — expected for
# test-first development.
from app.services.bid_package_list_service import (
    BidPackageListValidationError,
    list_bid_packages,
)

from .conftest import (
    PACKAGE_CLOSED_ID,
    PACKAGE_EVALUATING_ID,
    PACKAGE_OPEN_ID,
    PROJECT_A_ID,
    PROJECT_B_ID,
    build_chain,
)


class TestNoFilters:
    """Returns all packages with denormalized project/task names + counts."""

    @pytest.mark.asyncio
    async def test_returns_all_rows(self, mock_supabase):
        items = await list_bid_packages(
            db=mock_supabase,
            status=None,
            project_id=None,
            sort_by="deadline",
            sort_order="asc",
        )
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_each_item_has_denormalized_names(self, mock_supabase):
        items = await list_bid_packages(
            db=mock_supabase,
            status=None,
            project_id=None,
            sort_by="deadline",
            sort_order="asc",
        )

        ids_to_item = {str(item["id"]): item for item in items}

        open_item = ids_to_item[str(PACKAGE_OPEN_ID)]
        assert open_item["task_name"] == "Rough Grading"
        assert open_item["project_name"] == "Alpine Estates"
        assert str(open_item["project_id"]) == str(PROJECT_A_ID)

        closed_item = ids_to_item[str(PACKAGE_CLOSED_ID)]
        assert closed_item["task_name"] == "Site Survey"
        assert closed_item["project_name"] == "Birch Park"
        assert str(closed_item["project_id"]) == str(PROJECT_B_ID)

    @pytest.mark.asyncio
    async def test_each_item_has_required_fields(self, mock_supabase):
        items = await list_bid_packages(
            db=mock_supabase,
            status=None,
            project_id=None,
            sort_by="deadline",
            sort_order="asc",
        )
        for item in items:
            for key in (
                "id",
                "task_id",
                "task_name",
                "project_id",
                "project_name",
                "round_number",
                "deadline",
                "status",
                "total_invitations",
                "submitted_count",
                "created_at",
            ):
                assert key in item, f"missing {key}"


class TestStatusFilter:
    """`status` query is applied via .eq on bid_packages.status."""

    @pytest.mark.asyncio
    async def test_filter_passed_to_supabase(self, mock_supabase, sample_rows):
        chain = build_chain(data=[r for r in sample_rows if r["status"] == "open"])
        mock_supabase.table.side_effect = lambda _n: chain

        items = await list_bid_packages(
            db=mock_supabase,
            status="open",
            project_id=None,
            sort_by="deadline",
            sort_order="asc",
        )

        eq_calls = [tuple(c.args) for c in chain.eq.call_args_list]
        assert ("status", "open") in eq_calls
        assert len(items) == 1
        assert items[0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_invalid_status_raises_400(self, mock_supabase):
        with pytest.raises(BidPackageListValidationError) as exc:
            await list_bid_packages(
                db=mock_supabase,
                status="not-a-real-status",
                project_id=None,
                sort_by="deadline",
                sort_order="asc",
            )
        assert exc.value.status_code == 400


class TestProjectFilter:
    """`project_id` query filters via the embedded tasks.project_id."""

    @pytest.mark.asyncio
    async def test_filter_passed_to_supabase(self, mock_supabase, sample_rows):
        chain = build_chain(
            data=[
                r for r in sample_rows
                if r["tasks"]["project_id"] == str(PROJECT_A_ID)
            ]
        )
        mock_supabase.table.side_effect = lambda _n: chain

        items = await list_bid_packages(
            db=mock_supabase,
            status=None,
            project_id=PROJECT_A_ID,
            sort_by="deadline",
            sort_order="asc",
        )

        eq_calls = [tuple(c.args) for c in chain.eq.call_args_list]
        assert ("tasks.project_id", str(PROJECT_A_ID)) in eq_calls
        assert len(items) == 2
        for item in items:
            assert str(item["project_id"]) == str(PROJECT_A_ID)


class TestSort:
    """Sort options applied via .order or in-memory for project_name."""

    @pytest.mark.asyncio
    async def test_default_sort_is_deadline_asc(self, mock_supabase, sample_rows):
        chain = build_chain(data=sample_rows)
        mock_supabase.table.side_effect = lambda _n: chain

        await list_bid_packages(
            db=mock_supabase,
            status=None,
            project_id=None,
            sort_by="deadline",
            sort_order="asc",
        )

        order_calls = [
            (c.args, c.kwargs) for c in chain.order.call_args_list
        ]
        assert any(
            args == ("deadline",) and kwargs.get("desc") is False
            for args, kwargs in order_calls
        )

    @pytest.mark.asyncio
    async def test_created_at_desc(self, mock_supabase, sample_rows):
        chain = build_chain(data=sample_rows)
        mock_supabase.table.side_effect = lambda _n: chain

        await list_bid_packages(
            db=mock_supabase,
            status=None,
            project_id=None,
            sort_by="created_at",
            sort_order="desc",
        )

        order_calls = [
            (c.args, c.kwargs) for c in chain.order.call_args_list
        ]
        assert any(
            args == ("created_at",) and kwargs.get("desc") is True
            for args, kwargs in order_calls
        )

    @pytest.mark.asyncio
    async def test_project_name_in_memory_sort(self, mock_supabase):
        items = await list_bid_packages(
            db=mock_supabase,
            status=None,
            project_id=None,
            sort_by="project_name",
            sort_order="asc",
        )
        names = [item["project_name"] for item in items]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_project_name_in_memory_sort_desc(self, mock_supabase):
        items = await list_bid_packages(
            db=mock_supabase,
            status=None,
            project_id=None,
            sort_by="project_name",
            sort_order="desc",
        )
        names = [item["project_name"] for item in items]
        assert names == sorted(names, reverse=True)

    @pytest.mark.asyncio
    async def test_invalid_sort_by_raises_400(self, mock_supabase):
        with pytest.raises(BidPackageListValidationError) as exc:
            await list_bid_packages(
                db=mock_supabase,
                status=None,
                project_id=None,
                sort_by="some_garbage_column",
                sort_order="asc",
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_sort_order_raises_400(self, mock_supabase):
        with pytest.raises(BidPackageListValidationError) as exc:
            await list_bid_packages(
                db=mock_supabase,
                status=None,
                project_id=None,
                sort_by="deadline",
                sort_order="sideways",
            )
        assert exc.value.status_code == 400


class TestCounts:
    """`total_invitations` and `submitted_count` come from the embed counts —
    the service must not issue a second `bid_invitations` query."""

    @pytest.mark.asyncio
    async def test_counts_are_taken_from_embed(self, mock_supabase):
        items = await list_bid_packages(
            db=mock_supabase,
            status=None,
            project_id=None,
            sort_by="deadline",
            sort_order="asc",
        )
        ids_to_item = {str(item["id"]): item for item in items}

        open_item = ids_to_item[str(PACKAGE_OPEN_ID)]
        assert open_item["total_invitations"] == 5
        assert open_item["submitted_count"] == 2

        eval_item = ids_to_item[str(PACKAGE_EVALUATING_ID)]
        assert eval_item["total_invitations"] == 4
        assert eval_item["submitted_count"] == 4

    @pytest.mark.asyncio
    async def test_no_second_bid_invitations_query(self, mock_supabase):
        await list_bid_packages(
            db=mock_supabase,
            status=None,
            project_id=None,
            sort_by="deadline",
            sort_order="asc",
        )
        # Service should only ever call .table("bid_packages").
        called_tables = [c.args[0] for c in mock_supabase.table.call_args_list]
        assert "bid_invitations" not in called_tables, (
            "service must not issue a separate bid_invitations query — "
            "counts come from the aliased embed"
        )


class TestEmptyResult:
    """No matching rows → empty list, no error."""

    @pytest.mark.asyncio
    async def test_empty_list(self, mock_supabase_empty):
        items = await list_bid_packages(
            db=mock_supabase_empty,
            status=None,
            project_id=None,
            sort_by="deadline",
            sort_order="asc",
        )
        assert items == []
