"""
Vendor performance review write path (Phase 10 final piece).

One PM rating (1-5) per completed contract. A single-row insert, so it goes
straight through the service_role client rather than an RPC (house convention:
RPCs are reserved for multi-row atomic writes; see contract_service and the
milestone RPCs). `vendor_id` is resolved server-side from the contract — never
trusted from the client — with the DB trigger (fn_enforce_review_vendor_consistency)
as a backstop, not the gate.

Guards:
  - the contract must be `completed` (the rating panel only appears post-complete)
  - one review per contract (UNIQUE(contract_id) → 23505 → 409)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

logger = logging.getLogger(__name__)


class ReviewError(Exception):
    """Raised on review-write failure; the router maps it to an HTTPException.
    Mirrors ContractError / MilestoneError."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _first(data: Any) -> dict | None:
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _is_unique_violation(err: APIError) -> bool:
    """Postgres 23505 — the UNIQUE(contract_id) already has a review."""
    code = getattr(err, "code", None)
    msg = str(err).lower()
    return code == "23505" or "duplicate key" in msg or "unique" in msg


def create_review(
    *,
    contract_id: str,
    rating: int,
    notes: str | None,
    reviewed_by: str,
    db: Client,
) -> dict:
    """Insert the one review for a completed contract.

    Resolves vendor_id from the contract (server-side, never from the client),
    enforces the completed-only and one-per-contract guards, and returns the row.
    """
    contract = (
        db.table("contracts")
        .select("id, status, vendor_id")
        .eq("id", str(contract_id))
        .maybe_single()
        .execute()
    )
    contract_row = _first(contract.data)
    if not contract_row:
        raise ReviewError(404, "Contract not found.")

    if contract_row.get("status") != "completed":
        raise ReviewError(
            409, "A vendor can only be rated on a completed contract."
        )

    insert_row = {
        "contract_id": str(contract_id),
        "vendor_id": str(contract_row["vendor_id"]),  # server-resolved
        "rating": rating,
        "notes": notes,
        "reviewed_by": str(reviewed_by),
    }
    try:
        resp = db.table("vendor_performance_reviews").insert(insert_row).execute()
    except APIError as exc:
        if _is_unique_violation(exc):
            raise ReviewError(
                409, "This contract has already been reviewed."
            ) from exc
        logger.error("Review insert failed: %s", exc)
        raise ReviewError(422, "The review could not be saved.") from exc

    row = _first(resp.data)
    if not row:
        raise ReviewError(500, "Review creation failed.")
    return row


def update_review(
    *,
    review_id: str,
    changes: dict[str, Any],
    reviewed_by: str,
    db: Client,
) -> dict:
    """Correct an existing rating. `changes` holds only the fields the caller
    actually sent (router passes model_dump(exclude_unset=True)), so an omitted
    field is left untouched while an explicit `notes: null` clears the note.
    `reviewed_at`/`reviewed_by` always advance to record who set the CURRENT rating
    (created_at stays frozen at first-existence; updated_at is trigger-handled)."""
    update_data: dict[str, Any] = {
        "reviewed_by": str(reviewed_by),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    # Only rating/notes are writable here; ignore anything unexpected.
    for field in ("rating", "notes"):
        if field in changes:
            update_data[field] = changes[field]

    try:
        resp = (
            db.table("vendor_performance_reviews")
            .update(update_data)
            .eq("id", str(review_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Review update failed: %s", exc)
        raise ReviewError(422, "The review could not be updated.") from exc

    row = _first(resp.data)
    if not row:
        raise ReviewError(404, "Review not found.")
    return row
