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
from starlette.concurrency import run_in_threadpool
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


def _validate_signer(db: Client, signer_id) -> None:
    """The BluOnX signer chosen by the PM must be a live roster entry.

    An unknown id would only surface as an FK violation inside fn_create_award;
    a deactivated one would not surface at all and would quietly route the
    contract to someone who no longer signs. Both are 422 here instead.
    """
    resp = (
        db.table("contract_signers")
        .select("id, is_active")
        .eq("id", str(signer_id))
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise AwardError(422, "The selected contract signer does not exist.")
    if not rows[0].get("is_active"):
        raise AwardError(
            422,
            "The selected contract signer is deactivated. Choose an active signer.",
        )


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
    contract_valid_days: int | None = None,
    work_duration_days: int | None = None,
    signer_id: UUID,
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
    #     Offloaded: supabase-py is synchronous, so run the query in the
    #     threadpool to keep it off the event loop (matches the chain fetch + RPC).
    if await run_in_threadpool(lambda: _has_pending_revision(db, package.get("id"))):
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

    # 3b) The chosen BluOnX signer must exist and still be active. This is
    #     checked here, at award time, and not at envelope-send: the send is a
    #     post-commit best-effort hook whose exceptions are all swallowed, so a
    #     signer problem discovered there would vanish into a log line and leave
    #     the contract unroutable with nothing surfaced to the PM.
    await run_in_threadpool(lambda: _validate_signer(db, signer_id))

    # 4) Write the award row + flip the task to 'awarded' atomically via the
    #    fn_create_award RPC. A plpgsql function body is one implicit
    #    transaction, so the INSERT and the task UPDATE commit or roll back
    #    together — PostgREST can't express a multi-statement transaction over
    #    two .execute() calls, which is why a dedicated function is used here
    #    (see SECTION 7 in database/bluonx_complete_schema.sql). Server-derived
    #    fields only. The supabase client is synchronous; offload to the
    #    threadpool so the write can't stall the event loop.
    rpc_params = {
        "p_task_id": str(task_id),
        "p_bid_submission_id": str(bid_submission_id),
        "p_vendor_id": str(vendor_id),
        "p_awarded_by": str(awarded_by),
        "p_award_amount": _str_amount(context.award_amount),
        "p_has_override": has_override_final,
        "p_override_justification": justification_final,
        "p_instructions": (instructions or "").strip() or None,
        # Contract-term parameters. Default validity to 365 in the
        # service so the persisted 1-year term is explicit (COALESCE in the RPC
        # is the backstop); work_duration_days passes through nullable.
        "p_contract_valid_days": contract_valid_days if contract_valid_days is not None else 365,
        "p_work_duration_days": work_duration_days,
        "p_validation_results": _json_safe(result),
        # fn_create_award's twelfth parameter. It has no DEFAULT, and PostgREST
        # resolves an RPC by its named-argument set, so omitting this key means
        # no overload matches and the call fails outright.
        "p_signer_id": str(signer_id),
    }
    try:
        award_resp = await run_in_threadpool(
            lambda: db.rpc("fn_create_award", rpc_params).execute()
        )
    except APIError as exc:
        # idx_awards_one_active_per_task (a second active award) bubbles up as a
        # 23505 through the RPC and rolls the whole transaction back.
        if _is_unique_violation(exc):
            raise AwardError(
                409,
                "An active award already exists for this task.",
            ) from exc
        raise

    # RETURNS SETOF awards → PostgREST returns a JSON array of the one inserted
    # row; tolerate a bare dict too.
    data = award_resp.data
    award = (data[0] if isinstance(data, list) else data) or None
    if not award:
        raise AwardError(500, "Award creation failed.")

    # 5) Post-commit, best-effort: send the contract envelope (9.3b) + award email
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
