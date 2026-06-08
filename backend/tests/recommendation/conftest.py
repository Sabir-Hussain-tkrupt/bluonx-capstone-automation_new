"""Shared factories for Task 8.4 recommendation-builder tests.

The recommendation builder is pure (cohort dict → recommendation dict), so
these factories build the minimum row-shape it needs — no FakeSupabase, no
HTTP client.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4


def make_row(
    *,
    bid_submission_id: UUID | str | None = None,
    vendor_company_name: str | None = "Acme Co.",
    total_weighted_score: str | float | None = "80.00",
    this_total: str | float | None = "100000.00",
    sub_scores: dict[str, float] | None = None,
    # inputs (mirrors what bid_scoring_service writes into scoring_metadata.inputs)
    onboarding_status: str | None = "complete",
    insurance_expiration: date | None = date(2026, 12, 31),
    deadline: date | None = date(2026, 7, 1),
    max_active_jobs: int | None = 5,
    current_active_jobs: int = 1,
    proposed_start_date: date | None = date(2026, 7, 15),
    desired_start_date: date | None = date(2026, 7, 15),
    basis: str | None = None,
) -> dict[str, Any]:
    """Build one BidScoreResponse-shaped dict — matches what GET /scores returns
    per-row, including `vendor_company_name` and the full `scoring_metadata`."""
    if bid_submission_id is None:
        bid_submission_id = uuid4()
    sub_scores = sub_scores or {
        "price": 80.0,
        "compliance": 80.0,
        "performance": 75.0,
        "capacity": 80.0,
        "timeline": 100.0,
    }
    inputs = {
        "this_total": str(this_total) if this_total is not None else None,
        "lowest_valid_total": str(this_total) if this_total is not None else None,
        "onboarding_status": onboarding_status,
        "insurance_expiration": (
            insurance_expiration.isoformat() if insurance_expiration else None
        ),
        "deadline": deadline.isoformat() if deadline else None,
        "max_active_jobs": max_active_jobs,
        "current_active_jobs": current_active_jobs,
        "proposed_start_date": (
            proposed_start_date.isoformat() if proposed_start_date else None
        ),
        "desired_start_date": (
            desired_start_date.isoformat() if desired_start_date else None
        ),
    }
    metadata: dict[str, Any] = {
        "rubric_version": "v1.0",
        "weights": {
            "price": 0.50,
            "compliance": 0.05,
            "performance": 0.20,
            "capacity": 0.10,
            "timeline": 0.15,
        },
        "inputs": inputs,
        "sub_scores": sub_scores,
        "cohort_size": 1,
        "computed_at": "2026-07-02T12:00:00+00:00",
    }
    if basis is not None:
        metadata["basis"] = basis
    return {
        "id": str(uuid4()),
        "bid_submission_id": str(bid_submission_id),
        "price_score": f"{sub_scores['price']:.2f}",
        "compliance_score": f"{sub_scores['compliance']:.2f}",
        "performance_score": f"{sub_scores['performance']:.2f}",
        "capacity_score": f"{sub_scores['capacity']:.2f}",
        "timeline_score": f"{sub_scores['timeline']:.2f}",
        "total_weighted_score": (
            str(total_weighted_score) if total_weighted_score is not None else None
        ),
        "scoring_metadata": metadata,
        "scored_at": "2026-07-02T12:00:00+00:00",
        "scored_by": None,
        "vendor_company_name": vendor_company_name,
    }
