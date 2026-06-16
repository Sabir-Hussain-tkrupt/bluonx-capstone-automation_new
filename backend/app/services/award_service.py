"""
Award-create write path + validation override gate (Task 9.2).

The first real writer to `awards`. It recomputes the Task 9.1 pre-award
validation fresh server-side (never trusting a client-supplied snapshot) and
gates the write:

  block            → 422 (returns the result; not overridable)
  warn + no/blank justification → 422 (returns the full result; forces the dialog)
  warn + justification          → write with has_override = TRUE  + snapshot
  all clean                     → write with has_override = FALSE + snapshot

award_amount / task_id / vendor_id / awarded_by are all derived server-side from
the submission chain. The award row is written at `pending_acceptance` and the
task flipped to `awarded`. No DocuSign, email, or contract — those are 9.3–9.6.

Writes are single-statement supabase-py ops (no db.rpc / explicit transaction) —
the DB triggers + partial unique indexes are the integrity backstop, matching
the rest of the codebase. The partial unique index idx_awards_one_active_per_task
is surfaced as a clean 409, not a 500.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

logger = logging.getLogger(__name__)

from app.services.pre_award_validation_service import (
    _embed_one,
    context_from_row,
    fetch_submission_chain_row,
    validate_pre_award,
)

# Package states from which an award may be made. Awarding from an `open`
# package (bidding still live) or a `cancelled` one is a precondition failure.
_AWARDABLE_PACKAGE_STATUSES = ("closed", "evaluating")


class AwardError(Exception):
    """Raised on award-create failure. Mirrors PreAwardError / the other
    service validation errors — the router translates it to an HTTPException.
    `detail` may be a string (preconditions, 409) or the full validation result
    dict (block / warn gate) so the override dialog can render it."""

    def __init__(self, status_code: int, detail) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


def _has_pending_revision(db: Client, bid_package_id) -> bool:
    """True if any invitation on this package has a pending revision request.
    Awarding while a revision is outstanding would race the vendor's in-flight
    edit, so award-create rejects it (409). `bid_revision_requests` keys on
    `bid_invitation_id`, so we filter through the bid_invitations embed."""
    if not bid_package_id:
        return False
    resp = (
        db.table("bid_revision_requests")
        .select("id, bid_invitations!inner(bid_package_id)")
        .eq("bid_invitations.bid_package_id", str(bid_package_id))
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def _is_unique_violation(err: APIError) -> bool:
    """Heuristic — supabase-py wraps Postgres 23505 in APIError. Same logic as
    bid_revision_service._is_unique_violation."""
    code = getattr(err, "code", None)
    msg = str(err).lower()
    return code == "23505" or "duplicate key" in msg or "unique" in msg


def _json_safe(result: dict) -> dict:
    """Make the validation result safe for JSONB storage. Per-check `inputs`
    are already string/None; only the top-level `award_amount` is a raw Decimal,
    so coerce it to a string (matches the bid_scores.scoring_metadata convention
    of stringifying decimals before insert)."""
    amount = result.get("award_amount")
    return {
        **result,
        "award_amount": str(amount) if isinstance(amount, Decimal) else amount,
    }


async def create_award(
    *,
    bid_submission_id: UUID,
    has_override: bool,
    override_justification: str | None,
    instructions: str | None = None,
    awarded_by: str,
    db: Client,
) -> dict:
    """Validate-gate and write the award for `bid_submission_id`. Returns the
    inserted award row. Raises AwardError on any precondition / gate failure."""
    # 1) Resolve the submission chain once; reuse it for both the write
    #    identifiers and the validation context.
    row = await fetch_submission_chain_row(bid_submission_id, db=db)  # 404 if missing

    vendor_id = row.get("vendor_id")
    package = _embed_one(_embed_one(row.get("bid_invitations")).get("bid_packages"))
    task = _embed_one(package.get("tasks"))
    task_id = task.get("id")
    package_status = package.get("status")

    # 2) Structural precondition: the package must be done collecting bids.
    if package_status not in _AWARDABLE_PACKAGE_STATUSES:
        raise AwardError(
            422,
            f"Cannot award from a bid package with status '{package_status}'. "
            "The package must be closed or evaluating.",
        )

    # 2b) Don't award while a vendor still has an outstanding revision request —
    #     the in-flight edit must be resolved (submitted/declined/cancelled) first.
    if _has_pending_revision(db, package.get("id")):
        raise AwardError(
            409,
            "Resolve the outstanding revision request before awarding.",
        )

    # 3) Recompute validation fresh — the server is the final truth.
    context = context_from_row(row)
    result = validate_pre_award(context)

    if result["has_blocking"]:
        # Block is never overridable; return the result so the UI shows why.
        raise AwardError(422, _json_safe(result))

    if result["has_warnings"]:
        if not has_override or not (override_justification or "").strip():
            # Force the override dialog with the full result.
            raise AwardError(422, _json_safe(result))
        has_override_final = True
        justification_final: str | None = override_justification.strip()
    else:
        # No warnings ⇒ override is a no-op regardless of what the client sent.
        has_override_final = False
        justification_final = None

    # 4) Write the award row (server-derived fields only).
    insert_row = {
        "task_id": str(task_id),
        "bid_submission_id": str(bid_submission_id),
        "vendor_id": str(vendor_id),
        "awarded_by": str(awarded_by),
        "award_amount": _str_amount(context.award_amount),
        "has_override": has_override_final,
        "override_justification": justification_final,
        "instructions": (instructions or "").strip() or None,
        "validation_results": _json_safe(result),
        "status": "pending_acceptance",
    }
    try:
        award_resp = db.table("awards").insert(insert_row).execute()
    except APIError as exc:
        if _is_unique_violation(exc):
            raise AwardError(
                409,
                "An active award already exists for this task.",
            ) from exc
        raise

    award = (award_resp.data or [None])[0]
    if not award:
        raise AwardError(500, "Award creation failed.")

    # 5) Flip the task to awarded. Single-statement op, consistent with the
    #    rest of the codebase (no cross-table transaction primitive available).
    db.table("tasks").update({"status": "awarded"}).eq("id", str(task_id)).execute()

    # 6) Post-commit, best-effort: send the contract envelope (9.3b) + award email
    #    (9.4) and create the contract row (9.5). A DocuSign/PDF/email failure must
    #    NOT roll back the award — it stays pending_acceptance with no envelope and
    #    is retryable via POST /awards/{id}/send-contract. Local import avoids any
    #    import cycle (the envelope service imports nothing from award_service).
    try:
        from app.services.contract_envelope_service import send_contract_envelope

        await send_contract_envelope(award["id"], db=db)
    except Exception:
        logger.exception(
            "Contract envelope send failed for award %s (award stands; resendable)",
            award.get("id"),
        )

    return award


def _str_amount(amount: Decimal | None) -> str | None:
    """awards.award_amount is NOT NULL numeric; PostgREST coerces a string. We
    stringify to avoid json.dumps choking on a raw Decimal."""
    return str(amount) if amount is not None else None
