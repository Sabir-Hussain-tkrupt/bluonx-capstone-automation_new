"""
Contract-signer roster management (admin-only writes).

Reads are deliberately absent: both the settings page and the award-screen
dropdown read `contract_signers` straight from Supabase, where
`contract_signers_select_authenticated` already lets any active user see every
row (including inactive ones). A FastAPI read would be a second path to the same
data.

Two invariants live here rather than in the database:

  G1 (last signer)  — the roster can never be emptied of active entries, because
                      an award cannot be created without one. Mirrors
                      `_guard_last_admin` in user_service.
  G2 (reactivation) — email is UNIQUE across active AND inactive rows, so an
                      admin re-adding someone they previously revoked hits a
                      collision. That is a different situation from a live
                      duplicate and gets its own message.

There is no delete. Revocation is `is_active = FALSE`, and `awards.signer_id` is
ON DELETE RESTRICT anyway.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, status
from postgrest.exceptions import APIError
from supabase import Client

from app.models.contract_signers import ContractSignerCreate, ContractSignerUpdate

logger = logging.getLogger(__name__)

_DUPLICATE_ACTIVE = "A contract signer with this email already exists."
_DUPLICATE_INACTIVE = (
    "A contract signer with this email already exists but is deactivated. "
    "Reactivate the existing entry instead of adding a new one."
)


def _is_unique_violation(exc: APIError) -> bool:
    msg = str(exc).lower()
    return (
        getattr(exc, "code", None) == "23505"
        or "duplicate key" in msg
        or "unique" in msg
    )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _find_by_email(db: Client, email: str) -> dict | None:
    resp = (
        db.table("contract_signers")
        .select("id, is_active")
        .eq("email", email)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _count_active_signers(db: Client) -> int:
    """Number of signers available to award against. Counted from the returned
    rows (not count=exact) so it behaves identically under the test fake."""
    resp = (
        db.table("contract_signers")
        .select("id")
        .eq("is_active", True)
        .execute()
    )
    return len(resp.data or [])


def _guard_last_signer(db: Client, *, deactivating: bool) -> None:
    """G1. Block an operation that would leave zero active signers — no task
    could be awarded until someone added one back."""
    if deactivating and _count_active_signers(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot deactivate the last active contract signer.",
        )


def _get_signer_row(db: Client, signer_id: UUID) -> dict:
    resp = (
        db.table("contract_signers")
        .select("*")
        .eq("id", str(signer_id))
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contract signer not found"
        )
    return rows[0]


def create_signer(db: Client, payload: ContractSignerCreate) -> dict:
    email = _normalize_email(str(payload.email))
    full_name = payload.full_name.strip()
    title = (payload.title or "").strip() or None

    # G2. Distinguish "already on the roster" from "revoked, reactivate it".
    existing = _find_by_email(db, email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_DUPLICATE_ACTIVE if existing.get("is_active") else _DUPLICATE_INACTIVE,
        )

    insert_row = {"full_name": full_name, "email": email, "title": title}
    try:
        resp = db.table("contract_signers").insert(insert_row).execute()
    except APIError as exc:
        # Backstop for the race between the probe above and this insert.
        if _is_unique_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_ACTIVE
            ) from exc
        logger.error("Supabase insert failed for contract_signers %s: %s", email, exc)
        raise

    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Contract signer creation failed.",
        )
    return rows[0]


def update_signer(db: Client, signer_id: UUID, patch: ContractSignerUpdate) -> dict:
    target = _get_signer_row(db, signer_id)

    # G1 first, so the more fundamental refusal wins its message.
    _guard_last_signer(
        db, deactivating=patch.is_active is False and bool(target.get("is_active"))
    )

    update: dict = patch.model_dump(exclude_unset=True)
    if "email" in update and update["email"] is not None:
        update["email"] = _normalize_email(str(update["email"]))
    if "full_name" in update and update["full_name"] is not None:
        update["full_name"] = update["full_name"].strip()
    if "title" in update and update["title"] is not None:
        update["title"] = update["title"].strip() or None

    if not update:
        # Nothing to change; return the current row rather than issue an empty write.
        return target

    try:
        resp = (
            db.table("contract_signers")
            .update(update)
            .eq("id", str(signer_id))
            .execute()
        )
    except APIError as exc:
        if _is_unique_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_ACTIVE
            ) from exc
        logger.error("Supabase update failed for contract_signers %s: %s", signer_id, exc)
        raise

    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contract signer not found"
        )
    return rows[0]
