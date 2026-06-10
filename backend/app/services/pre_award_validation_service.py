"""
Pre-award validation for competitive bid awards (Task 9.1).

Six PURE per-check functions (each: inputs -> a self-describing check dict, no
DB) plus `validate_pre_award`, which runs them over a resolved `PreAwardContext`
and derives the award-gate flags. A separate loader owns all I/O, resolving the
context server-side from a candidate `bid_submission_id` — the validator never
sees a request body. This mirrors the 8.2 scoring discipline: deterministic,
independently unit-testable logic with the I/O pushed to the edge.

The returned result object is byte-compatible with what `awards.validation_results`
(JSONB) stores at award time and what 9.2's override UI renders, so every check
carries a raw `inputs` blob and stays interpretable as a stored snapshot.

Gate semantics (defined here; ENFORCED at award-create in 9.2/9.5, not here):
  any block  → can_award = false (hard-reject, not overridable)
  any warn   → requires_override = true (PM proceeds with justification)
  pass/skip  → clean award.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from supabase import Client

# ── Constants ────────────────────────────────────────────────────────────

RUBRIC_VERSION = "preaward-v1"

# ±5% band around tasks.budget_estimate.
BUDGET_VARIANCE_BAND = 0.05

# A candidate is "live" only in these submission states.
ELIGIBLE_STATUSES = ("submitted", "under_review", "accepted")


# ── Exceptions ───────────────────────────────────────────────────────────


class PreAwardError(Exception):
    """Raised when the context can't be loaded. Maps to HTTPException in router."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ── Context ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PreAwardContext:
    """Everything `validate_pre_award` needs, resolved server-side by the loader.

    `today` is injected (not read from the clock inside the validator) so the
    insurance check stays pure and deterministically testable.
    """

    award_amount: Decimal | None  # = candidate submission's total_amount
    is_superseded: bool
    is_draft: bool
    submission_status: str | None
    proposed_start_date: date | None
    insurance_expiration_date: date | None
    bonding_capacity: Decimal | None
    max_active_jobs: int | None
    current_active_jobs: int
    budget_estimate: Decimal | None
    estimated_end_date: date | None  # projects.estimated_end_date
    desired_start_date: date | None
    today: date


# ── Check-result helpers ─────────────────────────────────────────────────

# status is derived from severity: pass→pass, skipped→skipped, warn/block→fail.
_STATUS_FOR = {"pass": "pass", "skipped": "skipped", "warn": "fail", "block": "fail"}


def _check(check: str, severity: str, message: str, inputs: dict) -> dict:
    return {
        "check": check,
        "severity": severity,
        "status": _STATUS_FOR[severity],
        "message": message,
        "inputs": inputs,
    }


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d is not None else None


def _str_decimal(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


# ── Pure per-check functions ─────────────────────────────────────────────


def check_submission_eligibility(
    *, is_superseded: bool, is_draft: bool, status: str | None
) -> dict:
    """Candidate must be live: not superseded, not draft, status in the live set.
    Anything else → BLOCK. Subsumes the awards.py create-time superseded guard."""
    inputs = {
        "is_superseded": is_superseded,
        "is_draft": is_draft,
        "status": status,
        "eligible_statuses": list(ELIGIBLE_STATUSES),
    }
    if is_superseded:
        return _check(
            "submission_eligibility", "block",
            "This submission has been superseded by a newer revision; award the latest version.",
            inputs,
        )
    if is_draft:
        return _check(
            "submission_eligibility", "block",
            "This submission is still a draft and cannot be awarded.",
            inputs,
        )
    if status not in ELIGIBLE_STATUSES:
        return _check(
            "submission_eligibility", "block",
            f"Submission status {status!r} is not awardable.",
            inputs,
        )
    return _check(
        "submission_eligibility", "pass", "Submission is live and awardable.", inputs
    )


def check_insurance_validity(
    *,
    insurance_expiration_date: date | None,
    estimated_end_date: date | None,
    today: date,
) -> dict:
    """Insurance vs today and vs the project end date.
      expired (< today)                      → BLOCK (uninsurable; not overridable)
      valid today but lapses before est. end → WARN
      est_end NULL → compare to today only   → PASS
      expiration NULL                        → WARN (data gap)
    """
    inputs = {
        "insurance_expiration_date": _iso(insurance_expiration_date),
        "estimated_end_date": _iso(estimated_end_date),
        "today": _iso(today),
    }
    if insurance_expiration_date is None:
        return _check(
            "insurance_validity", "warn",
            "Vendor has no insurance expiration on file; verify the certificate.",
            inputs,
        )
    if insurance_expiration_date < today:
        return _check(
            "insurance_validity", "block",
            "Vendor insurance is expired; awarding is uninsurable liability.",
            inputs,
        )
    if estimated_end_date is not None and insurance_expiration_date < estimated_end_date:
        return _check(
            "insurance_validity", "warn",
            "Vendor insurance lapses before the project's estimated end date.",
            inputs,
        )
    return _check(
        "insurance_validity", "pass", "Vendor insurance is valid.", inputs
    )


def check_bonding_capacity(
    *, bonding_capacity: Decimal | None, award_amount: Decimal | None
) -> dict:
    """Bonding capacity vs award amount.
      capacity NULL              → WARN (data gap)
      capacity < award_amount    → WARN (insufficient bonding)
      else                       → PASS
    """
    inputs = {
        "bonding_capacity": _str_decimal(bonding_capacity),
        "award_amount": _str_decimal(award_amount),
    }
    if bonding_capacity is None:
        return _check(
            "bonding_capacity", "warn",
            "Vendor bonding capacity is not on file.",
            inputs,
        )
    if award_amount is not None and bonding_capacity < award_amount:
        return _check(
            "bonding_capacity", "warn",
            "Vendor bonding capacity is below this contract value.",
            inputs,
        )
    return _check(
        "bonding_capacity", "pass", "Vendor bonding capacity is sufficient.", inputs
    )


def check_vendor_capacity(
    *, max_active_jobs: int | None, current_active_jobs: int
) -> dict:
    """Current vs max active jobs.
      max NULL                       → SKIPPED (uncollected data; don't penalize)
      current >= max                 → WARN (at/over capacity)
      else                           → PASS
    App code never mutates capacity — the +1 is the award trigger's job.
    """
    inputs = {
        "max_active_jobs": max_active_jobs,
        "current_active_jobs": current_active_jobs,
    }
    if max_active_jobs is None:
        return _check(
            "vendor_capacity", "skipped",
            "Vendor max active jobs not set; capacity not evaluated.",
            inputs,
        )
    if current_active_jobs >= max_active_jobs:
        return _check(
            "vendor_capacity", "warn",
            "Vendor is at or over its active-job capacity.",
            inputs,
        )
    return _check(
        "vendor_capacity", "pass", "Vendor has available capacity.", inputs
    )


def check_budget_variance(
    *, award_amount: Decimal | None, budget_estimate: Decimal | None
) -> dict:
    """Award amount vs task budget estimate, ±5% band.
      budget_estimate NULL                       → SKIPPED
      |award - estimate| / estimate > 0.05       → WARN (direction + variance_pct)
      else                                       → PASS
    """
    inputs: dict[str, Any] = {
        "award_amount": _str_decimal(award_amount),
        "budget_estimate": _str_decimal(budget_estimate),
        "band_pct": BUDGET_VARIANCE_BAND * 100.0,
    }
    if budget_estimate is None or budget_estimate == 0 or award_amount is None:
        return _check(
            "budget_variance", "skipped",
            "No budget estimate on the task; variance not evaluated.",
            inputs,
        )
    delta = award_amount - budget_estimate
    variance = abs(delta) / budget_estimate
    inputs["variance_pct"] = round(float(variance) * 100.0, 2)
    inputs["direction"] = "over" if delta > 0 else "under"
    if float(variance) > BUDGET_VARIANCE_BAND:
        return _check(
            "budget_variance", "warn",
            f"Award amount is {inputs['variance_pct']}% {inputs['direction']} the budget estimate.",
            inputs,
        )
    return _check(
        "budget_variance", "pass", "Award amount is within the budget band.", inputs
    )


def check_start_date_feasibility(
    *, proposed_start_date: date | None, desired_start_date: date | None
) -> dict:
    """Proposed start vs the package's desired start (8.1.5 calendar data).
      desired NULL                       → SKIPPED (no target)
      proposed NULL while desired present → WARN (guard the gap)
      proposed > desired                 → WARN (with days_late)
      else                               → PASS
    """
    inputs: dict[str, Any] = {
        "proposed_start_date": _iso(proposed_start_date),
        "desired_start_date": _iso(desired_start_date),
    }
    if desired_start_date is None:
        return _check(
            "start_date_feasibility", "skipped",
            "No desired start date on the package; start date not evaluated.",
            inputs,
        )
    if proposed_start_date is None:
        return _check(
            "start_date_feasibility", "warn",
            "Vendor did not commit a proposed start date.",
            inputs,
        )
    days_late = (proposed_start_date - desired_start_date).days
    inputs["days_late"] = days_late
    if days_late > 0:
        return _check(
            "start_date_feasibility", "warn",
            f"Vendor's proposed start is {days_late} day(s) after the desired start.",
            inputs,
        )
    return _check(
        "start_date_feasibility", "pass",
        "Vendor can start on or before the desired date.", inputs
    )


# ── Validator ────────────────────────────────────────────────────────────


def validate_pre_award(context: PreAwardContext) -> dict:
    """Run all six checks over `context` and derive the award-gate flags.

    Returns the result object snapshotted into awards.validation_results at
    award time (9.5) and rendered by the override UI (9.2).
    """
    checks = [
        check_submission_eligibility(
            is_superseded=context.is_superseded,
            is_draft=context.is_draft,
            status=context.submission_status,
        ),
        check_insurance_validity(
            insurance_expiration_date=context.insurance_expiration_date,
            estimated_end_date=context.estimated_end_date,
            today=context.today,
        ),
        check_bonding_capacity(
            bonding_capacity=context.bonding_capacity,
            award_amount=context.award_amount,
        ),
        check_vendor_capacity(
            max_active_jobs=context.max_active_jobs,
            current_active_jobs=context.current_active_jobs,
        ),
        check_budget_variance(
            award_amount=context.award_amount,
            budget_estimate=context.budget_estimate,
        ),
        check_start_date_feasibility(
            proposed_start_date=context.proposed_start_date,
            desired_start_date=context.desired_start_date,
        ),
    ]

    has_blocking = any(c["severity"] == "block" for c in checks)
    has_warnings = any(c["severity"] == "warn" for c in checks)

    return {
        "rubric_version": RUBRIC_VERSION,
        "can_award": not has_blocking,
        "has_blocking": has_blocking,
        "has_warnings": has_warnings,
        "requires_override": has_warnings and not has_blocking,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "award_amount": context.award_amount,
        "checks": checks,
    }


# ── Loader (owns all I/O) ────────────────────────────────────────────────


def _unwrap_single(data: Any) -> dict | None:
    """PostgREST `.maybe_single()` can return dict, list, or None."""
    if data is None:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _embed_one(value: Any) -> dict:
    """A to-one PostgREST embed arrives as a dict (or a 1-element list)."""
    if isinstance(value, list):
        return value[0] if value else {}
    if isinstance(value, dict):
        return value
    return {}


def _parse_date(value: Any) -> date | None:
    """Parse a PostgREST ISO date/timestamp into a `date`. None/'' → None."""
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return date.fromisoformat(s[:10])


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


async def load_pre_award_context(
    bid_submission_id: UUID, *, db: Client
) -> PreAwardContext:
    """Resolve the full pre-award context from a candidate submission id.

    Walks bid_submissions → bid_invitations → bid_packages → tasks → projects
    plus vendors in one nested PostgREST select. Unknown submission → 404.
    (`onboarding_status` is loaded for snapshot completeness but no 9.1 check
    consumes it.)
    """
    resp = (
        db.table("bid_submissions")
        .select(
            "total_amount, proposed_start_date, vendor_id, is_draft,"
            " is_superseded, status, is_direct_assign,"
            " vendors!inner(insurance_expiration_date, bonding_capacity,"
            " max_active_jobs, current_active_jobs, onboarding_status),"
            " bid_invitations!inner(bid_packages!inner(desired_start_date,"
            " deadline, status, tasks!inner(budget_estimate, project_id,"
            " projects!inner(estimated_end_date))))"
        )
        .eq("id", str(bid_submission_id))
        .maybe_single()
        .execute()
    )
    row = _unwrap_single(resp.data)
    if row is None:
        raise PreAwardError(404, "Bid submission not found")

    vendor = _embed_one(row.get("vendors"))
    invitation = _embed_one(row.get("bid_invitations"))
    package = _embed_one(invitation.get("bid_packages"))
    task = _embed_one(package.get("tasks"))
    project = _embed_one(task.get("projects"))

    return PreAwardContext(
        award_amount=_to_decimal(row.get("total_amount")),
        is_superseded=bool(row.get("is_superseded")),
        is_draft=bool(row.get("is_draft")),
        submission_status=row.get("status"),
        proposed_start_date=_parse_date(row.get("proposed_start_date")),
        insurance_expiration_date=_parse_date(vendor.get("insurance_expiration_date")),
        bonding_capacity=_to_decimal(vendor.get("bonding_capacity")),
        max_active_jobs=vendor.get("max_active_jobs"),
        current_active_jobs=vendor.get("current_active_jobs") or 0,
        budget_estimate=_to_decimal(task.get("budget_estimate")),
        estimated_end_date=_parse_date(project.get("estimated_end_date")),
        desired_start_date=_parse_date(package.get("desired_start_date")),
        today=date.today(),
    )
