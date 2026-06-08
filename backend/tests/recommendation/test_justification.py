"""Justification-string tests for Task 8.4 recommendation builder."""

from __future__ import annotations

from decimal import Decimal

from app.services.bid_recommendation_service import build_recommendation

from .conftest import make_row


def test_justification_mentions_company_and_total():
    row = make_row(
        vendor_company_name="Acme Co.",
        total_weighted_score="87.50",
    )
    justification = build_recommendation([row], Decimal("500000"))["justification"]
    assert "Acme Co." in justification
    assert "87.50" in justification


def test_justification_references_winning_dimension():
    """Winner has price=100, others at 50; price gets called out."""
    winner_subs = {
        "price": 100.0, "compliance": 80.0, "performance": 75.0,
        "capacity": 80.0, "timeline": 100.0,
    }
    loser_subs = {
        "price": 50.0, "compliance": 80.0, "performance": 75.0,
        "capacity": 80.0, "timeline": 50.0,
    }
    rows = [
        make_row(bid_submission_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                 total_weighted_score="92.00", sub_scores=winner_subs),
        make_row(bid_submission_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                 total_weighted_score="60.00", sub_scores=loser_subs),
    ]
    justification = build_recommendation(rows, Decimal("500000"))["justification"]
    assert "lowest price" in justification
    assert "100/100" in justification


def test_justification_does_not_praise_weak_dimensions():
    """Winner leads on compliance=40 but it's below threshold; should not appear."""
    winner_subs = {
        "price": 95.0, "compliance": 40.0, "performance": 60.0,
        "capacity": 60.0, "timeline": 95.0,
    }
    loser_subs = {
        "price": 50.0, "compliance": 30.0, "performance": 60.0,
        "capacity": 60.0, "timeline": 50.0,
    }
    rows = [
        make_row(total_weighted_score="80.00", sub_scores=winner_subs),
        make_row(total_weighted_score="50.00", sub_scores=loser_subs),
    ]
    justification = build_recommendation(rows, Decimal("500000"))["justification"]
    assert "compliance" not in justification.lower()


def test_lone_bidder_justification_is_sensible():
    """Single-row cohort: winner trivially leads everything; threshold gates
    out the genuinely weak dimensions but praises the strong ones."""
    subs = {
        "price": 100.0, "compliance": 100.0, "performance": 75.0,
        "capacity": 80.0, "timeline": 100.0,
    }
    row = make_row(vendor_company_name="Solo Vendor",
                   total_weighted_score="90.00",
                   sub_scores=subs)
    justification = build_recommendation([row], Decimal("500000"))["justification"]
    assert "Solo Vendor" in justification
    assert "lowest price" in justification or "strongest timeline" in justification


def test_justification_fallback_label_when_company_name_missing():
    """No vendor_company_name → graceful fallback (not 'None recommended')."""
    row = make_row(vendor_company_name=None, total_weighted_score="80.00")
    justification = build_recommendation([row], Decimal("500000"))["justification"]
    assert "None" not in justification
