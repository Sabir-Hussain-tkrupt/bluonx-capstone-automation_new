"""Task 8.4: pure recommendation builder.

Input  : enriched scored cohort (BidScoreResponse-shaped dicts with
         `vendor_company_name` and full `scoring_metadata`) + `budget_estimate`.
Output : ranking + justification + per-vendor warning flags — or None for an
         empty cohort.

No DB, no I/O. Deterministic. The builder is the data layer for the Task 8.3
compare/recommendation UI and is unit-testable in isolation.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.bid_scoring_service import INSURANCE_HORIZON_DAYS


WARNING_CODES: tuple[str, ...] = (
    "over_budget",
    "late_start",
    "insurance_window",
    "onboarding_incomplete",
)

DIMENSION_LABELS: list[tuple[str, str]] = [
    ("price", "lowest price"),
    ("timeline", "strongest timeline"),
    ("compliance", "best compliance"),
    ("capacity", "best capacity"),
    ("performance", "strongest past performance"),
]

HIGHLIGHT_THRESHOLD = 75.0


# ── Public entry point ──────────────────────────────────────────────────


def build_recommendation(
    scores: list[dict],
    budget_estimate: Decimal | str | int | float | None,
) -> dict | None:
    """Build the recommendation envelope, or None for an empty cohort."""
    if not scores:
        return None

    ranked = _rank(scores)
    budget_d = _to_decimal(budget_estimate)

    ranking = [
        {
            "rank": i + 1,
            "bid_submission_id": row["bid_submission_id"],
            "vendor_company_name": row.get("vendor_company_name"),
            "total_weighted_score": row.get("total_weighted_score"),
            "this_total": _read_this_total(row),
            "warning_flags": _flags_for(row, budget_d),
        }
        for i, row in enumerate(ranked)
    ]

    return {
        "recommended_bid_submission_id": ranking[0]["bid_submission_id"],
        "justification": _build_justification(ranked),
        "ranking": ranking,
    }


# ── Ranking + tie-break ─────────────────────────────────────────────────


_NEG_INF = Decimal("-1E18")  # sorts to the bottom (None total_weighted_score)
_POS_INF = Decimal("1E18")   # sorts to the bottom (None this_total)


def _rank(scores: list[dict]) -> list[dict]:
    """Sort by total_weighted_score desc; tie-break by this_total asc; then
    by stringified bid_submission_id for fully deterministic order."""

    def key(r: dict):
        tw = _to_decimal(r.get("total_weighted_score"))
        primary = -(tw if tw is not None else _NEG_INF)
        tt = _read_this_total(r)
        secondary = tt if tt is not None else _POS_INF
        return (primary, secondary, str(r.get("bid_submission_id") or ""))

    return sorted(scores, key=key)


# ── Warning flags ───────────────────────────────────────────────────────


def _flags_for(row: dict, budget_d: Decimal | None) -> list[str]:
    md = row.get("scoring_metadata") or {}
    inputs = md.get("inputs") or {}
    flags: list[str] = []

    # 1. over_budget — suppressed when budget is NULL.
    this_total = _read_this_total(row)
    if budget_d is not None and this_total is not None and this_total > budget_d:
        flags.append("over_budget")

    # 2. late_start — suppressed by basis OR missing dates.
    if md.get("basis") != "no_desired_date":
        proposed = _parse_date(inputs.get("proposed_start_date"))
        desired = _parse_date(inputs.get("desired_start_date"))
        if proposed is not None and desired is not None and proposed > desired:
            flags.append("late_start")

    # 3. insurance_window — NULL expiration flags; otherwise flag when
    #    expiration < deadline + 30d. (deadline + 30d is the safe boundary,
    #    matching the 8.2 rubric's score=100 threshold.)
    exp = _parse_date(inputs.get("insurance_expiration"))
    deadline = _parse_date(inputs.get("deadline"))
    if exp is None:
        flags.append("insurance_window")
    elif deadline is not None and exp < deadline + timedelta(
        days=INSURANCE_HORIZON_DAYS
    ):
        flags.append("insurance_window")

    # 4. onboarding_incomplete — anything that's not exactly "complete".
    if inputs.get("onboarding_status") != "complete":
        flags.append("onboarding_incomplete")

    return flags


# ── Justification ───────────────────────────────────────────────────────


def _build_justification(ranked: list[dict]) -> str:
    winner = ranked[0]
    company = winner.get("vendor_company_name") or "Top-ranked vendor"
    tw = winner.get("total_weighted_score")
    tw_str = _format_score(tw)

    parts = [f"{company} recommended on overall weighted score ({tw_str})."]

    sub_scores = (winner.get("scoring_metadata") or {}).get("sub_scores") or {}
    highlights: list[str] = []

    for key, label in DIMENSION_LABELS:
        w = _to_float(sub_scores.get(key))
        if w is None or w < HIGHLIGHT_THRESHOLD:
            continue
        # cohort leader: winner's score must be >= every other vendor's score
        # on this dimension. Lone-bidder degenerates to leading trivially.
        leader = True
        for r in ranked[1:]:
            other = _to_float(
                ((r.get("scoring_metadata") or {}).get("sub_scores") or {}).get(key)
            )
            if other is not None and other > w:
                leader = False
                break
        if leader:
            highlights.append(f"{label} ({w:.0f}/100)")

    if highlights:
        parts.append(" Leads on " + ", ".join(highlights) + ".")
    return "".join(parts)


# ── Helpers ─────────────────────────────────────────────────────────────


def _read_this_total(row: dict) -> Decimal | None:
    md = row.get("scoring_metadata") or {}
    inputs = md.get("inputs") or {}
    return _to_decimal(inputs.get("this_total"))


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _format_score(value: Any) -> str:
    d = _to_decimal(value)
    if d is None:
        return "n/a"
    return f"{d:.2f}"
