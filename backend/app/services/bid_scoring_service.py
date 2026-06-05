"""
Weighted scoring engine for competitive bid packages (Task 8.2).

Five PURE per-dimension functions (inputs -> 0-100 float, no DB) plus one
orchestrator that owns all I/O. Persists one bid_scores row per submission and
snapshots a scoring_metadata blob so old rows stay interpretable if weights
ever change.

Spec: docs/CURRENT_PHASE_TASKS.md Task 8.2.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from supabase import Client

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────

RUBRIC_VERSION = "v1.0"

WEIGHTS: dict[str, float] = {
    "price": 0.50,
    "compliance": 0.05,
    "performance": 0.20,
    "capacity": 0.10,
    "timeline": 0.15,
}

# Placeholder until Phase 10 (milestone-driven on-time rate + flag history).
# See /docs/DEFERRED.md > Past Performance Scoring.
NEUTRAL_PERFORMANCE_SCORE = 75.0

# Used when max_active_jobs is NULL — can't penalise for uncollected data.
NEUTRAL_CAPACITY_SCORE = 75.0

INSURANCE_HORIZON_DAYS = 30

ONBOARDING_SCORE: dict[str, float] = {
    "complete": 100.0,
    "partial": 50.0,
    "pending": 0.0,
}

COHORT_STATUSES = ("submitted", "under_review")

# (days_late_upper_bound, score) — first bucket where days_late <= bound wins.
TIMELINE_BUCKETS: list[tuple[int, float]] = [
    (0, 100.0),
    (7, 75.0),
    (14, 50.0),
    (30, 25.0),
]
TIMELINE_OVERAGE_SCORE = 0.0


# ── Exceptions ───────────────────────────────────────────────────────────


class BidScoringError(Exception):
    """Raised when scoring cannot proceed. Maps to HTTPException in router."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ── Pure dimension functions ─────────────────────────────────────────────


def score_price(this_total: Decimal, lowest_valid_total: Decimal) -> float:
    """Price: lowest/this × 100, clamped to ≤ 100."""
    if this_total <= 0:
        return 0.0
    raw = float(lowest_valid_total) / float(this_total) * 100.0
    return min(raw, 100.0)


def score_compliance(
    onboarding_status: str | None,
    insurance_expiration: date | None,
    deadline: date,
) -> float:
    """Mean of onboarding component and insurance-vs-horizon component."""
    onboarding_component = ONBOARDING_SCORE.get(onboarding_status or "", 0.0)

    if insurance_expiration is None:
        insurance_component = 0.0
    else:
        horizon = deadline + timedelta(days=INSURANCE_HORIZON_DAYS)
        if insurance_expiration >= horizon:
            insurance_component = 100.0
        elif insurance_expiration >= deadline:
            insurance_component = 50.0
        else:
            insurance_component = 0.0

    return (onboarding_component + insurance_component) / 2.0


def score_performance(vendor_id: UUID) -> float:
    """
    Past-performance score. Phase 10 placeholder.

    Real impl will combine on-time milestone completion rate (from milestone
    data landing in Phase 10) with vendor_flags history. The orchestrator,
    weights, metadata snapshot, and endpoint don't change — only this body.
    See /docs/DEFERRED.md > Past Performance Scoring.
    """
    return NEUTRAL_PERFORMANCE_SCORE


def score_capacity(
    max_active_jobs: int | None,
    current_active_jobs: int,
) -> float:
    """available / max * 100; NULL max → NEUTRAL; max==0 → 0."""
    if max_active_jobs is None:
        return NEUTRAL_CAPACITY_SCORE
    if max_active_jobs == 0:
        return 0.0
    available = max(max_active_jobs - current_active_jobs, 0)
    return available / max_active_jobs * 100.0


def score_timeline(
    proposed_start_date: date | None,
    desired_start_date: date | None,
) -> float:
    """
    desired NULL → 100 (cohort-constant, cancels out of ranking).
    desired present + proposed NULL → 0 (proposed is required at submit).
    else walk TIMELINE_BUCKETS against days_late.
    """
    if desired_start_date is None:
        return 100.0
    if proposed_start_date is None:
        return 0.0
    days_late = (proposed_start_date - desired_start_date).days
    for upper, score in TIMELINE_BUCKETS:
        if days_late <= upper:
            return score
    return TIMELINE_OVERAGE_SCORE


# ── Internal helpers ─────────────────────────────────────────────────────


def _unwrap_single(data: Any) -> dict | None:
    """PostgREST `.maybe_single()` / `.single()` can return dict, list, or None."""
    if data is None:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _parse_date(value: Any) -> date | None:
    """Parse a PostgREST ISO date/timestamp string into a `date`. None → None."""
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value)
    # Tolerate both 'YYYY-MM-DD' and full 'YYYY-MM-DDTHH:MM:SS+00:00'.
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return date.fromisoformat(s[:10])


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


# ── Orchestrator ─────────────────────────────────────────────────────────


async def score_bid_package(
    bid_package_id: UUID, *, scored_by: UUID | str, db: Client
) -> dict[str, Any]:
    """
    Score a competitive bid package's current submissions, upsert one
    bid_scores row per submission, and return the cohort.

    Errors (via BidScoringError):
      404 unknown package
      400 task.bid_type is not 'competitive'
      422 no valid submissions to score
    """
    bid_package_id_str = str(bid_package_id)

    # 1) Load package + bid_type via tasks join.
    pkg_resp = (
        db.table("bid_packages")
        .select("*, tasks!inner(bid_type)")
        .eq("id", bid_package_id_str)
        .maybe_single()
        .execute()
    )
    pkg = _unwrap_single(pkg_resp.data)
    if pkg is None:
        raise BidScoringError(404, "Bid package not found")

    task = pkg.get("tasks") or {}
    if isinstance(task, list):
        task = task[0] if task else {}
    bid_type = task.get("bid_type")
    if bid_type != "competitive":
        raise BidScoringError(
            400,
            f"Bid package is not competitive (bid_type={bid_type!r}); "
            "scoring is only meaningful for competitive packages.",
        )

    deadline_date = _parse_date(pkg.get("deadline"))
    desired_date = _parse_date(pkg.get("desired_start_date"))

    # 2) Resolve invitation ids for this package.
    inv_resp = (
        db.table("bid_invitations")
        .select("id")
        .eq("bid_package_id", bid_package_id_str)
        .execute()
    )
    invitation_ids = [row["id"] for row in (inv_resp.data or [])]
    if not invitation_ids:
        raise BidScoringError(422, "No valid submissions to score")

    # 3) Cohort: submissions on these invitations matching the rubric filters.
    sub_resp = (
        db.table("bid_submissions")
        .select(
            "*, vendors!inner(insurance_expiration_date, max_active_jobs, "
            "current_active_jobs, onboarding_status)"
        )
        .in_("bid_invitation_id", invitation_ids)
        .eq("is_superseded", False)
        .eq("is_draft", False)
        .in_("status", list(COHORT_STATUSES))
        .execute()
    )
    raw_subs = sub_resp.data or []

    # Filter null/zero totals in Python: Supabase numeric compare on a stringly
    # typed DECIMAL is fragile, and the check is cheap here.
    cohort: list[dict] = []
    for s in raw_subs:
        total = _to_decimal(s.get("total_amount"))
        if total is None or total <= 0:
            continue
        cohort.append(s)
    if not cohort:
        raise BidScoringError(422, "No valid submissions to score")

    submission_ids = [s["id"] for s in cohort]
    lowest = min(_to_decimal(s["total_amount"]) for s in cohort)

    # 4) Look up any existing bid_scores rows for these submissions so manual
    # adjustments are preserved on recompute.
    existing_resp = (
        db.table("bid_scores")
        .select("*")
        .in_("bid_submission_id", submission_ids)
        .execute()
    )
    existing = existing_resp.data or []
    manual_rows = [r for r in existing if r.get("scored_by") is not None]
    manual_ids = {r["bid_submission_id"] for r in manual_rows}

    # 5) Build score rows for everything except manual-adjusted submissions.
    cohort_size = len(cohort)
    computed_at = datetime.now(timezone.utc).isoformat()
    rows_to_upsert: list[dict] = []

    for sub in cohort:
        if sub["id"] in manual_ids:
            # TODO(Phase 8 manual-adjust feature): when the manual-adjust write
            # path lands, decide whether recompute is allowed to clobber based
            # on an explicit force-flag. For now, manual rows are sacred.
            continue

        vendor = sub.get("vendors") or {}
        this_total = _to_decimal(sub["total_amount"])
        insurance_exp = _parse_date(vendor.get("insurance_expiration_date"))
        proposed_date = _parse_date(sub.get("proposed_start_date"))
        max_jobs = vendor.get("max_active_jobs")
        current_jobs = vendor.get("current_active_jobs") or 0
        onboarding = vendor.get("onboarding_status")

        sub_scores = {
            "price": score_price(this_total, lowest),
            "compliance": score_compliance(
                onboarding, insurance_exp, deadline_date
            ),
            "performance": score_performance(UUID(sub["vendor_id"])),
            "capacity": score_capacity(max_jobs, current_jobs),
            "timeline": score_timeline(proposed_date, desired_date),
        }
        total_weighted = round(
            sum(WEIGHTS[k] * v for k, v in sub_scores.items()), 2
        )

        inputs_snapshot = {
            "this_total": str(this_total),
            "lowest_valid_total": str(lowest),
            "onboarding_status": onboarding,
            "insurance_expiration": (
                insurance_exp.isoformat() if insurance_exp else None
            ),
            "deadline": deadline_date.isoformat() if deadline_date else None,
            "max_active_jobs": max_jobs,
            "current_active_jobs": current_jobs,
            "proposed_start_date": (
                proposed_date.isoformat() if proposed_date else None
            ),
            "desired_start_date": (
                desired_date.isoformat() if desired_date else None
            ),
        }

        metadata: dict[str, Any] = {
            "rubric_version": RUBRIC_VERSION,
            "weights": WEIGHTS,
            "inputs": inputs_snapshot,
            "sub_scores": sub_scores,
            "cohort_size": cohort_size,
            "computed_at": computed_at,
        }
        if desired_date is None:
            metadata["basis"] = "no_desired_date"

        rows_to_upsert.append({
            "bid_submission_id": sub["id"],
            "price_score": f"{sub_scores['price']:.2f}",
            "compliance_score": f"{sub_scores['compliance']:.2f}",
            "performance_score": f"{sub_scores['performance']:.2f}",
            "capacity_score": f"{sub_scores['capacity']:.2f}",
            "timeline_score": f"{sub_scores['timeline']:.2f}",
            "total_weighted_score": f"{total_weighted:.2f}",
            "scoring_metadata": metadata,
            "scored_at": computed_at,
            "scored_by": None,  # system-generated
        })

    # 6) Upsert.
    upserted: list[dict] = []
    if rows_to_upsert:
        upsert_resp = (
            db.table("bid_scores")
            .upsert(rows_to_upsert, on_conflict="bid_submission_id")
            .execute()
        )
        upserted = upsert_resp.data or []

    # 7) Compose response: manual rows (untouched) + upserted rows.
    return {
        "bid_package_id": bid_package_id_str,
        "rubric_version": RUBRIC_VERSION,
        "cohort_size": cohort_size,
        "scores": manual_rows + upserted,
    }


# ── Read seam (Task 8.3/8.4): GET /bid-packages/{id}/scores ──────────────


def _empty_scores_response(bid_package_id_str: str, budget_estimate: Any) -> dict:
    return {
        "bid_package_id": bid_package_id_str,
        "rubric_version": RUBRIC_VERSION,
        "cohort_size": 0,
        "scores": [],
        "budget_estimate": budget_estimate,
        "valid_submission_count": 0,
        "latest_submission_at": None,
    }


async def get_bid_package_scores(
    bid_package_id: UUID,
    *,
    db: Client,
) -> dict:
    """Read persisted weighted scores for a competitive bid package, joined to
    the live non-superseded cohort. No recompute, no writes.

    Live-cohort join: query `bid_submissions` with `is_superseded=False,
    is_draft=False, status IN COHORT_STATUSES` and pull the embedded
    `bid_scores` relation. Score rows for now-superseded / draft / wrong-status
    submissions are never selected — orphan cleanup happens for free.

    Errors mirror POST's gates: 404 unknown package, 400 non-competitive.
    Diverges from POST on empty cohort: returns 200 with `scores: []` so the
    compare page can render its "Compute Rankings" CTA.
    """
    bid_package_id_str = str(bid_package_id)

    pkg_resp = (
        db.table("bid_packages")
        .select("id, tasks!inner(bid_type, budget_estimate)")
        .eq("id", bid_package_id_str)
        .maybe_single()
        .execute()
    )
    pkg = _unwrap_single(pkg_resp.data)
    if pkg is None:
        raise BidScoringError(404, "Bid package not found")

    task = pkg.get("tasks") or {}
    if isinstance(task, list):
        task = task[0] if task else {}
    bid_type = task.get("bid_type")
    if bid_type != "competitive":
        raise BidScoringError(
            400,
            f"Bid package is not competitive (bid_type={bid_type!r}); "
            "scoring is only meaningful for competitive packages.",
        )
    budget_estimate = task.get("budget_estimate")

    inv_resp = (
        db.table("bid_invitations")
        .select("id")
        .eq("bid_package_id", bid_package_id_str)
        .execute()
    )
    invitation_ids = [row["id"] for row in (inv_resp.data or [])]
    if not invitation_ids:
        return _empty_scores_response(bid_package_id_str, budget_estimate)

    sub_resp = (
        db.table("bid_submissions")
        .select(
            "id, total_amount, submitted_at,"
            " vendors!inner(company_name),"
            " bid_scores(*)"
        )
        .in_("bid_invitation_id", invitation_ids)
        .eq("is_superseded", False)
        .eq("is_draft", False)
        .in_("status", list(COHORT_STATUSES))
        .execute()
    )
    live = sub_resp.data or []

    valid_live: list[dict] = []
    latest_submission_at: str | None = None
    for s in live:
        amt = s.get("total_amount")
        if amt is None:
            continue
        try:
            if Decimal(str(amt)) <= 0:
                continue
        except Exception:
            continue
        valid_live.append(s)
        sub_at = s.get("submitted_at")
        if sub_at and (latest_submission_at is None or sub_at > latest_submission_at):
            latest_submission_at = sub_at

    scores: list[dict] = []
    for s in valid_live:
        vendor = s.get("vendors") or {}
        if isinstance(vendor, list):
            vendor = vendor[0] if vendor else {}
        company_name = vendor.get("company_name")

        score_rows = s.get("bid_scores") or []
        if isinstance(score_rows, dict):
            score_rows = [score_rows]
        for sr in score_rows:
            scores.append({**sr, "vendor_company_name": company_name})

    return {
        "bid_package_id": bid_package_id_str,
        "rubric_version": RUBRIC_VERSION,
        "cohort_size": len(scores),
        "scores": scores,
        "budget_estimate": budget_estimate,
        "valid_submission_count": len(valid_live),
        "latest_submission_at": latest_submission_at,
    }
