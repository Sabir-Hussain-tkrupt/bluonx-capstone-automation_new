"""Ranking + tie-break tests for Task 8.4 recommendation builder."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.services.bid_recommendation_service import build_recommendation

from .conftest import make_row


def test_empty_cohort_returns_none():
    assert build_recommendation([], Decimal("500000")) is None


def test_ranks_by_total_weighted_score_desc():
    rows = [
        make_row(bid_submission_id="11111111-1111-1111-1111-111111111111",
                 total_weighted_score="60.00", this_total="80000.00"),
        make_row(bid_submission_id="22222222-2222-2222-2222-222222222222",
                 total_weighted_score="90.00", this_total="100000.00"),
        make_row(bid_submission_id="33333333-3333-3333-3333-333333333333",
                 total_weighted_score="75.00", this_total="90000.00"),
    ]
    rec = build_recommendation(rows, Decimal("500000"))
    assert rec is not None
    ranking = rec["ranking"]
    assert [r["bid_submission_id"] for r in ranking] == [
        "22222222-2222-2222-2222-222222222222",  # 90
        "33333333-3333-3333-3333-333333333333",  # 75
        "11111111-1111-1111-1111-111111111111",  # 60
    ]
    assert [r["rank"] for r in ranking] == [1, 2, 3]


def test_tie_break_lower_this_total_wins():
    """Documented rule: same total_weighted_score → lower this_total wins."""
    rows = [
        make_row(bid_submission_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                 total_weighted_score="80.00", this_total="100000.00"),
        make_row(bid_submission_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                 total_weighted_score="80.00", this_total="90000.00"),
    ]
    rec = build_recommendation(rows, Decimal("500000"))
    assert rec["ranking"][0]["bid_submission_id"] == (
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    )


def test_tie_break_final_stable_by_bid_submission_id():
    """Same total + same this_total → string-UUID ordering, deterministic."""
    rows = [
        make_row(bid_submission_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                 total_weighted_score="80.00", this_total="90000.00"),
        make_row(bid_submission_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                 total_weighted_score="80.00", this_total="90000.00"),
    ]
    rec = build_recommendation(rows, Decimal("500000"))
    assert [r["bid_submission_id"] for r in rec["ranking"]] == [
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    ]


def test_recommended_id_matches_ranking_zero():
    rows = [
        make_row(total_weighted_score="60.00"),
        make_row(total_weighted_score="95.00"),
        make_row(total_weighted_score="75.00"),
    ]
    rec = build_recommendation(rows, Decimal("500000"))
    assert rec["recommended_bid_submission_id"] == rec["ranking"][0]["bid_submission_id"]


def test_lone_bidder_one_rank_no_false_alternatives():
    """Single-row cohort: ranking has length 1, no fabricated #2/#3."""
    rows = [make_row(bid_submission_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
                     total_weighted_score="80.00")]
    rec = build_recommendation(rows, Decimal("500000"))
    assert rec is not None
    assert len(rec["ranking"]) == 1
    assert rec["ranking"][0]["rank"] == 1
    assert rec["recommended_bid_submission_id"] == (
        "cccccccc-cccc-cccc-cccc-cccccccccccc"
    )


def test_none_total_weighted_score_sorts_last():
    """Defensive: a row with NULL total ranks at the bottom, not the top."""
    rows = [
        make_row(bid_submission_id="11111111-1111-1111-1111-111111111111",
                 total_weighted_score=None),
        make_row(bid_submission_id="22222222-2222-2222-2222-222222222222",
                 total_weighted_score="50.00"),
    ]
    rec = build_recommendation(rows, Decimal("500000"))
    assert rec["ranking"][0]["bid_submission_id"] == (
        "22222222-2222-2222-2222-222222222222"
    )
    assert rec["ranking"][1]["bid_submission_id"] == (
        "11111111-1111-1111-1111-111111111111"
    )


def test_ranked_vendor_fields_propagate():
    """rank/bid_submission_id/vendor_company_name/total_weighted_score/this_total
    all surface on each ranked row."""
    rows = [make_row(vendor_company_name="Acme Co.",
                     total_weighted_score="80.00",
                     this_total="95000.00")]
    rec = build_recommendation(rows, Decimal("500000"))
    r0 = rec["ranking"][0]
    assert r0["vendor_company_name"] == "Acme Co."
    assert Decimal(str(r0["total_weighted_score"])) == Decimal("80.00")
    assert Decimal(str(r0["this_total"])) == Decimal("95000.00")
    assert "warning_flags" in r0
    assert isinstance(r0["warning_flags"], list)
