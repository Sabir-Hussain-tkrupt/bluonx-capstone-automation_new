"""Bid award → budget line hooks (Phase 2 · Task 2.5).

Three moments of the EXISTING award / DocuSign flow move money in the budget:

  award created              → fn_apply_bid_to_line   (line = award; Δ ↔ contingency)
  DocuSign declined / voided → fn_reverse_bid_on_line (undo the above)
  DocuSign completed         → fn_lock_budget_line    (lock; dates from contract)

Contract for callers (award_service, docusign_webhooks):
  * Call the `safe_*` functions only, AFTER the existing work has committed.
  * They never raise and never change the caller's response: a budget problem
    must not fail an award or a DocuSign webhook (the award stands, exactly as
    the envelope-send hook already behaves). Failures are logged with the ids.
  * Every procedure is idempotent, so webhook retries are harmless.
  * `sync_project` (admin "Sync awards") repairs anything a hook missed and
    back-fills awards that existed before the budget was created.

Projects without a budget, and tasks without a live budget line, are skipped.
"""

from __future__ import annotations

import logging
from typing import Any

from supabase import Client

from app.services.financial_errors import FinancialError, call_rpc

logger = logging.getLogger(__name__)

_ACTIVE_AWARD = ("pending_acceptance", "accepted")
_EXECUTED_CONTRACT = ("executed", "active", "completed")


def _line_for_task(db: Client, task_id: Any) -> dict | None:
    rows = (
        db.table("budget_lines").select("*")
        .eq("task_id", str(task_id)).is_("deleted_at", "null").limit(1).execute()
    ).data or []
    return rows[0] if rows else None


def _project_has_budget(db: Client, project_id: Any) -> bool:
    resp = db.table("projects").select("budget_status").eq("id", str(project_id)).maybe_single().execute()
    return bool(resp and resp.data and resp.data.get("budget_status", "none") != "none")


def _award(db: Client, award_id: Any) -> dict | None:
    resp = db.table("awards").select("*").eq("id", str(award_id)).maybe_single().execute()
    return resp.data if resp else None


# ── Core operations (raise FinancialError) ──────────────────────────────────


def apply_award(db: Client, award: dict, actor_id: Any = None) -> str:
    line = _line_for_task(db, award["task_id"])
    if not line or line["line_type"] != "bid_activity" or not _project_has_budget(db, line["project_id"]):
        return "skipped"
    if str(line.get("award_id") or "") == str(award["id"]) and str(line["committed_amount"]) == str(award["award_amount"]):
        return "unchanged"
    call_rpc(
        db, "fn_apply_bid_to_line",
        {
            "p_budget_line_id": str(line["id"]),
            "p_award_id": str(award["id"]),
            "p_amount": str(award["award_amount"]),
            "p_actor": str(actor_id or award["awarded_by"]),
        },
        "The award could not be applied to the budget.",
    )
    return "applied"


def reverse_award(db: Client, award_id: Any, actor_id: Any = None, reason: str | None = None) -> str:
    rows = (
        db.table("budget_lines").select("*")
        .eq("award_id", str(award_id)).is_("deleted_at", "null").limit(1).execute()
    ).data or []
    if not rows:
        return "skipped"
    award = _award(db, award_id) or {}
    call_rpc(
        db, "fn_reverse_bid_on_line",
        {
            "p_budget_line_id": str(rows[0]["id"]),
            "p_award_id": str(award_id),
            "p_actor": str(actor_id or award.get("awarded_by")),
            "p_reason": reason,
        },
        "The award could not be reversed in the budget.",
    )
    return "reversed"


def lock_for_contract(db: Client, contract: dict, actor_id: Any = None) -> str:
    line = _line_for_task(db, contract["task_id"])
    if not line or line["line_type"] != "bid_activity" or not _project_has_budget(db, line["project_id"]):
        return "skipped"
    award = _award(db, contract["award_id"]) or {}
    actor = actor_id or award.get("awarded_by")
    # The award may never have reached the line (hook failed / budget created later).
    if str(line.get("award_id") or "") != str(contract["award_id"]) and award:
        if line.get("award_id"):
            reverse_award(db, line["award_id"], actor, "Replaced by the executed contract's award")
        apply_award(db, award, actor)
    if line.get("is_locked") and str(line.get("contract_id") or "") == str(contract["id"]):
        return "unchanged"
    call_rpc(
        db, "fn_lock_budget_line",
        {"p_budget_line_id": str(line["id"]), "p_contract_id": str(contract["id"]), "p_actor": str(actor)},
        "The budget line could not be locked.",
    )
    return "locked"


# ── Hook wrappers: never raise ──────────────────────────────────────────────


def safe_apply_award(db: Client, award: dict) -> str:
    try:
        return apply_award(db, award)
    except Exception:  # noqa: BLE001 - the award must stand regardless
        logger.exception("Budget hook: applying award %s to its budget line failed (use Sync awards)",
                         award.get("id"))
        return "failed"


def safe_reverse_award(db: Client, award_id: Any, reason: str) -> str:
    try:
        return reverse_award(db, award_id, None, reason)
    except Exception:  # noqa: BLE001 - the webhook result must not change
        logger.exception("Budget hook: reversing award %s failed (use Sync awards)", award_id)
        return "failed"


def safe_lock_for_contract(db: Client, contract_id: Any) -> str:
    try:
        resp = db.table("contracts").select("*").eq("id", str(contract_id)).maybe_single().execute()
        contract = resp.data if resp else None
        if not contract:
            return "skipped"
        return lock_for_contract(db, contract)
    except Exception:  # noqa: BLE001 - the webhook result must not change
        logger.exception("Budget hook: locking the line for contract %s failed (use Sync awards)", contract_id)
        return "failed"


# ── Safety net ──────────────────────────────────────────────────────────────


def sync_project(db: Client, project_id: Any, actor_id: Any) -> dict:
    """Bring every bid line of a project in line with its task's award / contract."""
    counts = {"applied": 0, "locked": 0, "failed": 0}
    lines = (
        db.table("budget_lines").select("*")
        .eq("project_id", str(project_id)).eq("line_type", "bid_activity")
        .is_("deleted_at", "null").execute()
    ).data or []
    for line in lines:
        if not line.get("task_id"):
            continue
        try:
            awards = (
                db.table("awards").select("*").eq("task_id", str(line["task_id"])).execute()
            ).data or []
            active = next((a for a in awards if a.get("status") in _ACTIVE_AWARD), None)
            current = str(line.get("award_id") or "")

            if current and (not active or str(active["id"]) != current):
                reverse_award(db, current, actor_id, "Award no longer active")
            if active and str(active["id"]) != current:
                if apply_award(db, active, actor_id) == "applied":
                    counts["applied"] += 1
            if active:
                contracts = (
                    db.table("contracts").select("*").eq("award_id", str(active["id"])).execute()
                ).data or []
                executed = next((c for c in contracts if c.get("status") in _EXECUTED_CONTRACT), None)
                if executed and lock_for_contract(db, executed, actor_id) == "locked":
                    counts["locked"] += 1
        except FinancialError as exc:
            counts["failed"] += 1
            logger.warning("Sync awards: line %s skipped: %s", line.get("id"), exc.detail)
    return counts
