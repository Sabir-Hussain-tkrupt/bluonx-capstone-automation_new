"""
Contract record lifecycle, built together with the envelope send (9.3b).

Per the "Contract lifecycle reframe" in CURRENT_PHASE_TASKS.md, the contracts row
is born at ENVELOPE-SEND time in `sent_for_signature` (not at acceptance) so the
NOT NULL `docusign_envelopes.contract_id` FK is satisfiable. This module owns the
row's transitions:

  create_contract_for_award  → INSERT at `sent_for_signature` (re-entrant)
  mark_contract_executed     → `executed` + signed_at (Connect `completed`)
  mark_contract_terminated   → `terminated` (decline / void)

Writes are single-statement supabase-py ops; the partial unique index
`idx_contracts_one_active_per_task` is surfaced as a clean 409 (mirrors the
award_service convention). No schema change.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

logger = logging.getLogger(__name__)


class ContractError(Exception):
    """Raised on contract-write failure; the router maps it to an HTTPException."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _is_unique_violation(err: APIError) -> bool:
    """Same heuristic as award_service._is_unique_violation (Postgres 23505)."""
    code = getattr(err, "code", None)
    msg = str(err).lower()
    return code == "23505" or "duplicate key" in msg or "unique" in msg


def _has_pt_code(err: APIError, pt: str) -> bool:
    """True when an RPC raised SQLSTATE `pt` (e.g. 'PT409'). Mirrors
    milestone_service._has_pt_code: supabase-py surfaces the raised SQLSTATE on
    APIError.code, and we scan the stringified error as a backstop."""
    code = str(getattr(err, "code", "") or "")
    return code == pt or pt in str(err)


def generate_contract_number(award_id: str) -> str:
    """Auto contract number. `CON-{YYYY}-{first 8 of the award id}` — unique
    (award_id is unique per active task), race-free, and needs no sequence table.
    Refining the human-facing scheme is left to 9.5 polish."""
    year = datetime.now(timezone.utc).year
    short = str(award_id).replace("-", "")[:8].upper()
    return f"CON-{year}-{short}"


def _str_amount(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value) if isinstance(value, Decimal) else str(value)


def _date_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return str(value)[:10]


def _first(data: Any) -> dict | None:
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def create_contract_for_award(
    award: dict,
    *,
    start_date: Any = None,
    end_date: Any = None,
    payment_terms: str | None = None,
    sow_signed_date: Any = None,
    db: Client,
) -> dict:
    """INSERT the contract row at `sent_for_signature`. Re-entrant: if a contract
    already exists for this award (`award_id` is UNIQUE), return it rather than
    re-inserting — so a best-effort resend after a partial failure is safe.

    `award` must carry: id, vendor_id, task_id, award_amount.
    `sow_signed_date` is realized from the awarded submission's sow_attested_at
    and lights the "Date of signed scope of work" line in the contract PDF.
    """
    award_id = award["id"]

    # Re-entrant guard — reuse an existing contract for this award.
    existing = (
        db.table("contracts").select("*").eq("award_id", str(award_id)).limit(1).execute()
    )
    found = _first(existing.data)
    if found:
        return found

    insert_row = {
        "award_id": str(award_id),
        "vendor_id": str(award["vendor_id"]),
        "task_id": str(award["task_id"]),
        "contract_number": generate_contract_number(award_id),
        "start_date": _date_str(start_date),
        "end_date": _date_str(end_date),
        "contract_amount": _str_amount(award.get("award_amount")),
        "payment_terms": payment_terms,
        "sow_signed_date": _date_str(sow_signed_date),
        "status": "sent_for_signature",
    }
    try:
        resp = db.table("contracts").insert(insert_row).execute()
    except APIError as exc:
        if _is_unique_violation(exc):
            raise ContractError(
                409, "An active contract already exists for this task."
            ) from exc
        raise

    row = _first(resp.data)
    if not row:
        raise ContractError(500, "Contract creation failed.")
    return row


def mark_contract_executed(
    contract_id: str, *, contract_valid_days: int | None = None, db: Client
) -> dict:
    """Connect `completed` → contract `executed`, signed_at = now, and
    valid_until = signed_at + contract_valid_days — the realized expiry, frozen at
    the moment of signing. Both dates share the single signed_at timestamp and are
    written in one update, so they can never drift. Defaults to a 365-day term when
    the award parameter is missing."""
    signed_at = datetime.now(timezone.utc)
    valid_days = contract_valid_days if contract_valid_days is not None else 365
    valid_until = (signed_at.date() + timedelta(days=int(valid_days))).isoformat()
    resp = (
        db.table("contracts")
        .update(
            {
                "status": "executed",
                "signed_at": signed_at.isoformat(),
                "valid_until": valid_until,
            }
        )
        .eq("id", str(contract_id))
        .execute()
    )
    return _first(resp.data) or {}


def mark_contract_terminated(contract_id: str, *, db: Client) -> dict:
    """Decline / void → contract `terminated` (frees the task to re-award)."""
    resp = (
        db.table("contracts")
        .update({"status": "terminated"})
        .eq("id", str(contract_id))
        .execute()
    )
    return _first(resp.data) or {}


def mark_contract_completed(contract_id: str, *, db: Client) -> dict:
    """PM marks the work done → contract `completed`, via the row-locked
    `fn_mark_contract_complete` RPC. The gate ("every milestone completed/cancelled,
    none open") is re-checked inside the lock, so the check and the write can never
    race. The RPC is the sole authority — this layer only maps SQLSTATEs:
    PT404 → 404, PT409 → 409 (a milestone is still open, or the contract is already
    complete / terminated). No raw DB error surfaces."""
    try:
        resp = db.rpc(
            "fn_mark_contract_complete", {"p_contract_id": str(contract_id)}
        ).execute()
    except APIError as exc:
        if _has_pt_code(exc, "PT404"):
            raise ContractError(404, "Contract not found.") from exc
        if _has_pt_code(exc, "PT409"):
            raise ContractError(
                409,
                "Cannot complete: a milestone is still open, or the contract is "
                "already complete or terminated.",
            ) from exc
        logger.error("Unexpected contract-complete RPC failure: %s", exc)
        raise ContractError(502, "Contract completion failed.") from exc

    row = _first(resp.data)
    if not row:
        raise ContractError(500, "Contract completion failed.")
    return row
