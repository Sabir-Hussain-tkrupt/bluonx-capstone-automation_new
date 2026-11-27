"""Contingency engine (Phase 3 · Module 3).

The money rules live in the database (see migration 20261121):
  * contingency = pct of the base (total − land − contingency), recalculated on
    draft budgets whenever the base changes (fin_recalc_draft_contingency);
  * bid differences move in / out of contingency in fn_apply_bid_to_line, and
    the baselined-budget guard stops savings moving to another line;
  * every movement is an append-only contingency_ledger row;
  * top-ups are executive-only (fn_approve_contingency_top_up).

This module reads those tables for the panel and the ledger, works out the
running balance per contingency bucket (initial + each top-up), and calls the
procedures. Notifications are sent by contingency_notifications after a write.
"""

from __future__ import annotations

import csv
import io
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from supabase import Client

from app.core.auth import user_has_any_role
from app.services.financial_errors import FinancialError, call_rpc, first

_ACTIVE_AWARD = ("pending_acceptance", "accepted")
_BID_TYPES = ("competitive", "direct_assign")
_FUNDING = ("initial_funding", "top_up")
_CENT = Decimal("0.01")

MOVEMENT_LABELS = {
    "initial_funding": "Initial contingency",
    "bid_overrun": "Bid over budget",
    "bid_savings": "Bid savings",
    "bid_reversal": "Award reversed",
    "variance_created": "Variance",
    "variance_adjusted": "Variance adjusted",
    "variance_cancelled": "Variance cancelled",
    "top_up": "Top-up",
    "invoice_overage": "Invoice overage",
    "long_tail": "Escrow / property tax",
}

SETTING_DEFAULTS: dict[str, Any] = {
    "default_contingency_percent": 15,
    "bidding_target_contingency_percent": 10,
    "bidding_escalation_percent": 5,
    "default_field_approval_limit": 5000,
    "contingency_near_zero_percent": 5,
    "alert_escalation_days": 2,
    "alert_recipients": {"warning": [], "urgent": [], "critical": []},
    "executive_approval_threshold": None,
    "land_team_emails": [],
    "po_number_format": "PO-{YYYY}-{SEQ:05}",
    "po_number_format_contract": "{CONTRACT}-{SEQ:03}",
    "quickbooks_expense_account": "Job Expenses",
    "bond_renewal_reminder_days": 60,
    "finance_emails": [],
    "sales_emails": [],
}


# ── Small helpers ───────────────────────────────────────────────────────────


def _d(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def _money(value: Decimal | None) -> str | None:
    return None if value is None else str(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def _pct(part: Decimal, whole: Decimal) -> str | None:
    if whole <= 0:
        return None
    return str((part * 100 / whole).quantize(_CENT, rounding=ROUND_HALF_UP))


def is_executive(user: dict) -> bool:
    """Top-up approval is executive-only: an admin role alone is not enough."""
    held = set(user.get("roles") or []) | {user.get("role")}
    return "executive" in held


def can_manage_bidding(user: dict) -> bool:
    return user_has_any_role(user, "project_manager")


def get_settings(db: Client) -> dict[str, Any]:
    rows = (
        db.table("financial_settings").select("setting_key, value")
        .in_("setting_key", list(SETTING_DEFAULTS)).execute()
    ).data or []
    out = dict(SETTING_DEFAULTS)
    for row in rows:
        if row.get("value") is not None:
            out[row["setting_key"]] = row["value"]
    return out


def update_settings(db: Client, changes: dict[str, Any], actor_id: str) -> dict[str, Any]:
    for key, value in changes.items():
        if key not in SETTING_DEFAULTS or value is None:
            continue
        if key == "executive_approval_threshold" and value == "off":
            value = "off"  # stored as text: not a number, so no threshold
        if isinstance(value, Decimal):
            value = float(value) if value != value.to_integral_value() else int(value)
        db.table("financial_settings").upsert(
            {"setting_key": key, "value": value, "updated_by": actor_id},
            on_conflict="setting_key",
        ).execute()
    return get_settings(db)


def _project(db: Client, project_id: str) -> dict:
    resp = (
        db.table("projects").select("*")
        .eq("id", project_id).is_("deleted_at", "null").maybe_single().execute()
    )
    if not resp or not resp.data:
        raise FinancialError(404, "Project not found")
    return resp.data


def _users(db: Client, ids: set[str]) -> dict[str, dict]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = db.table("users").select("id, full_name, email").in_("id", list(ids)).execute().data or []
    return {str(r["id"]): r for r in rows}


def _name(users: dict[str, dict], user_id: Any) -> str | None:
    u = users.get(str(user_id)) if user_id else None
    return (u.get("full_name") or u.get("email")) if u else None


# ── Snapshot ────────────────────────────────────────────────────────────────


def snapshot(db: Client, project: dict, settings: dict[str, Any]) -> dict[str, Any]:
    lines = (
        db.table("budget_lines").select("line_type, budget_amount")
        .eq("project_id", project["id"]).is_("deleted_at", "null").execute()
    ).data or []
    cont = sum((_d(l["budget_amount"]) for l in lines if l["line_type"] == "contingency"), Decimal("0"))
    land = sum((_d(l["budget_amount"]) for l in lines if l["line_type"] == "land"), Decimal("0"))
    total = sum((_d(l["budget_amount"]) for l in lines), Decimal("0"))
    base = total - land - cont
    pct = project.get("contingency_percent")
    return {
        "contingency": _money(cont),
        "base": _money(base),
        "land": _money(land),
        "total": _money(total),
        "left_percent": _pct(cont, base),
        "contingency_percent": str(pct) if pct is not None else None,
        "effective_percent": str(pct if pct is not None else settings["default_contingency_percent"]),
        "default_percent": str(settings["default_contingency_percent"]),
        "target_percent": str(settings["bidding_target_contingency_percent"]),
        "escalation_percent": str(settings["bidding_escalation_percent"]),
    }


def outcome_for(left_percent: str | None, settings: dict[str, Any]) -> str:
    """Same rule as fn_complete_bidding, for the preview."""
    if left_percent is None:
        return "no_base"
    left = Decimal(left_percent)
    if left <= _d(settings["bidding_escalation_percent"]):
        return "escalated"
    if left < _d(settings["bidding_target_contingency_percent"]):
        return "below_target"
    return "on_target"


# ── Buckets and ledger ──────────────────────────────────────────────────────


def _buckets(db: Client, project_id: str) -> list[dict]:
    return (
        db.table("contingency_buckets").select("*")
        .eq("project_id", project_id).order("requested_at").execute()
    ).data or []


def _ledger_rows(db: Client, project_id: str) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        batch = (
            db.table("v_contingency_ledger").select("*")
            .eq("project_id", project_id).order("entry_no")
            .range(start, start + 999).execute()
        ).data or []
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        start += 1000


def build_ledger(db: Client, project_id: str) -> dict[str, Any]:
    """Ledger entries plus the running balance per bucket.

    Funding (initial, each approved top-up) fills its own bucket. Money going
    OUT is drawn from the oldest bucket that still has a balance (the last
    bucket goes negative once all are used up). Money coming back IN (savings,
    reversals, variance returns) refills the oldest bucket below its funded
    amount; anything beyond that stays in the initial bucket.
    """
    buckets = [b for b in _buckets(db, project_id) if b["status"] == "approved"]
    buckets.sort(key=lambda b: (b["bucket_kind"] != "initial", b.get("decided_at") or b["requested_at"]))
    state: dict[str, dict] = {}
    top_up_no = 0
    for b in buckets:
        if b["bucket_kind"] == "initial":
            label = "Initial contingency"
        else:
            top_up_no += 1
            label = f"Top-up {top_up_no}"
        state[str(b["id"])] = {
            "id": str(b["id"]),
            "kind": b["bucket_kind"],
            "label": label,
            "funded": Decimal("0"),
            "balance": Decimal("0"),
            "drawn": Decimal("0"),
            "returned": Decimal("0"),
            "reason": b.get("reason"),
            "decided_at": b.get("decided_at"),
        }
    order = list(state)

    entries: list[dict] = []
    total_in = total_out = Decimal("0")
    for row in _ledger_rows(db, project_id):
        amount = _d(row["amount"])
        allocations: list[tuple[str, Decimal]] = []
        bucket_id = str(row["contingency_bucket_id"]) if row.get("contingency_bucket_id") else None

        if row["movement_type"] in _FUNDING and bucket_id in state:
            s = state[bucket_id]
            s["funded"] += amount
            s["balance"] += amount
            allocations.append((bucket_id, amount))
        elif amount < 0 and order:
            need = -amount
            for bid in order:
                s = state[bid]
                if need <= 0:
                    break
                take = min(need, max(s["balance"], Decimal("0")))
                if take > 0:
                    s["balance"] -= take
                    s["drawn"] += take
                    allocations.append((bid, -take))
                    need -= take
            if need > 0:
                s = state[order[-1]]
                s["balance"] -= need
                s["drawn"] += need
                allocations.append((order[-1], -need))
            total_out += -amount
        elif amount > 0 and order:
            left = amount
            for bid in order:
                s = state[bid]
                room = s["funded"] - s["balance"]
                give = min(left, room) if room > 0 else Decimal("0")
                if give > 0:
                    s["balance"] += give
                    s["returned"] += give
                    allocations.append((bid, give))
                    left -= give
                if left <= 0:
                    break
            if left > 0:
                s = state[order[0]]
                s["balance"] += left
                s["returned"] += left
                allocations.append((order[0], left))
            total_in += amount
        elif amount > 0:
            total_in += amount
        elif amount < 0:
            total_out += -amount

        entries.append({
            "id": row["id"],
            "entry_no": row["entry_no"],
            "created_at": row["created_at"],
            "movement_type": row["movement_type"],
            "movement_label": MOVEMENT_LABELS.get(row["movement_type"], row["movement_type"]),
            "direction": row["direction"],
            "amount": _money(amount),
            "balance_before": _money(_d(row["balance_before"])),
            "balance_after": _money(_d(row["balance_after"])),
            "source_line_id": row.get("source_budget_line_id"),
            "source_line_name": row.get("source_line_name"),
            "actor_user_id": row.get("actor_user_id"),
            "actor_name": row.get("actor_name") or row.get("actor_email"),
            "reason": row.get("reason"),
            "allocations": [
                {
                    "bucket_id": bid,
                    "bucket_label": state[bid]["label"],
                    "amount": _money(amt),
                    "bucket_balance_after": _money(state[bid]["balance"]),
                }
                for bid, amt in allocations
            ],
        })

    bucket_out = [
        {
            "id": s["id"],
            "kind": s["kind"],
            "label": s["label"],
            "reason": s["reason"],
            "decided_at": s["decided_at"],
            "starting_amount": _money(s["funded"]),
            "drawn": _money(s["drawn"]),
            "returned": _money(s["returned"]),
            "remaining": _money(s["balance"]),
            "remaining_percent": _pct(s["balance"], s["funded"]),
        }
        for s in state.values()
    ]
    return {
        "entries": entries,
        "buckets": bucket_out,
        "total_in": _money(total_in),
        "total_out": _money(total_out),
    }


def ledger_csv(db: Client, project_id: str) -> tuple[str, bytes]:
    project = _project(db, project_id)
    ledger = build_ledger(db, project_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Entry", "Date", "Movement", "Direction", "Amount", "Balance before", "Balance after",
        "Source line", "Bucket(s)", "Bucket balance after", "User", "Reason",
    ])
    for e in ledger["entries"]:
        writer.writerow([
            e["entry_no"], e["created_at"], e["movement_label"], e["direction"], e["amount"],
            e["balance_before"], e["balance_after"], e["source_line_name"] or "",
            "; ".join(f'{a["bucket_label"]} {a["amount"]}' for a in e["allocations"]),
            "; ".join(f'{a["bucket_label"]} {a["bucket_balance_after"]}' for a in e["allocations"]),
            e["actor_name"] or "", e["reason"] or "",
        ])
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (project.get("name") or "project"))[:60]
    return f"contingency-ledger-{safe}.csv", buf.getvalue().encode("utf-8-sig")


# ── Top-ups ─────────────────────────────────────────────────────────────────


def _top_up_rows(db: Client, project_id: str) -> list[dict]:
    rows = [b for b in _buckets(db, project_id) if b["bucket_kind"] == "top_up"]
    users = _users(db, {str(r.get("requested_by") or "") for r in rows} | {str(r.get("decided_by") or "") for r in rows})
    return [
        {
            "id": r["id"],
            "status": r["status"],
            "requested_amount": _money(_d(r["requested_amount"])),
            "approved_amount": _money(_d(r["approved_amount"])) if r.get("approved_amount") is not None else None,
            "reason": r["reason"],
            "requested_by": r["requested_by"],
            "requested_by_name": _name(users, r["requested_by"]),
            "requested_at": r["requested_at"],
            "decided_by_name": _name(users, r.get("decided_by")),
            "decided_at": r.get("decided_at"),
            "decision_note": r.get("decision_note"),
        }
        for r in sorted(rows, key=lambda r: r["requested_at"], reverse=True)
    ]


def get_top_up(db: Client, bucket_id: str) -> dict:
    resp = db.table("contingency_buckets").select("*").eq("id", bucket_id).maybe_single().execute()
    if not resp or not resp.data or resp.data.get("bucket_kind") != "top_up":
        raise FinancialError(404, "Top-up request not found")
    return resp.data


def request_top_up(db: Client, *, project_id: str, amount: Decimal, reason: str, actor_id: str) -> dict:
    _project(db, project_id)
    data = call_rpc(
        db, "fn_request_contingency_top_up",
        {"p_project_id": project_id, "p_amount": str(amount), "p_reason": reason, "p_actor": actor_id},
        "The top-up request could not be saved.",
    )
    row = first(data)
    if not row:
        raise FinancialError(500, "The top-up request could not be saved.")
    return row


def decide_top_up(
    db: Client, *, bucket_id: str, approve: bool, approved_amount: Decimal | None, note: str | None, actor_id: str
) -> dict:
    get_top_up(db, bucket_id)
    data = call_rpc(
        db, "fn_approve_contingency_top_up",
        {
            "p_bucket_id": bucket_id,
            "p_approver": actor_id,
            "p_approve": approve,
            "p_approved_amount": str(approved_amount) if approved_amount is not None else None,
            "p_note": note,
        },
        "The top-up decision could not be saved.",
    )
    row = first(data)
    if not row:
        raise FinancialError(500, "The top-up decision could not be saved.")
    return row


def cancel_top_up(db: Client, *, bucket_id: str, user: dict) -> dict:
    bucket = get_top_up(db, bucket_id)
    if bucket["status"] != "pending":
        raise FinancialError(409, f"This top-up request is already {bucket['status']}.")
    if str(bucket["requested_by"]) != str(user["user_id"]) and user.get("role") != "admin":
        raise FinancialError(403, "Only the person who asked for the top-up, or an admin, can cancel it.")
    resp = (
        db.table("contingency_buckets").update({"status": "cancelled"})
        .eq("id", bucket_id).eq("status", "pending").execute()
    )
    rows = resp.data or []
    if not rows:
        raise FinancialError(409, "This top-up request was decided a moment ago.")
    return rows[0]


# ── Contingency % ───────────────────────────────────────────────────────────


def set_percent(db: Client, *, project_id: str, percent: Decimal | None, actor_id: str) -> dict:
    _project(db, project_id)
    return call_rpc(
        db, "fn_set_project_contingency_percent",
        {"p_project_id": project_id, "p_percent": str(percent) if percent is not None else None, "p_actor": actor_id},
        "The contingency % could not be changed.",
    ) or {}


# ── Bidding checkpoint ──────────────────────────────────────────────────────


def open_bid_tasks(db: Client, project_id: str) -> list[dict]:
    """Competitive / direct-assign tasks that still have no active award."""
    tasks = (
        db.table("tasks").select("id, name, bid_type, status")
        .eq("project_id", project_id).is_("deleted_at", "null")
        .in_("bid_type", list(_BID_TYPES)).order("sort_order").execute()
    ).data or []
    if not tasks:
        return []
    awarded: set[str] = set()
    ids = [str(t["id"]) for t in tasks]
    for i in range(0, len(ids), 200):
        rows = (
            db.table("awards").select("task_id")
            .in_("task_id", ids[i:i + 200]).in_("status", list(_ACTIVE_AWARD)).execute()
        ).data or []
        awarded.update(str(r["task_id"]) for r in rows)
    return [
        {"id": t["id"], "name": t["name"], "bid_type": t["bid_type"], "status": t.get("status")}
        for t in tasks if str(t["id"]) not in awarded
    ]


def checkpoint_preview(db: Client, project_id: str) -> dict:
    project = _project(db, project_id)
    settings = get_settings(db)
    snap = snapshot(db, project, settings)
    return {
        **snap,
        "budget_status": project.get("budget_status"),
        "bidding_completed_at": project.get("bidding_completed_at"),
        "open_tasks": open_bid_tasks(db, project_id),
        "predicted_outcome": outcome_for(snap["left_percent"], settings),
    }


def complete_bidding(db: Client, *, project_id: str, note: str | None, acknowledge: bool, actor_id: str) -> dict:
    _project(db, project_id)
    open_tasks = open_bid_tasks(db, project_id)
    if open_tasks and not acknowledge:
        names = ", ".join(t["name"] for t in open_tasks[:5])
        more = f" and {len(open_tasks) - 5} more" if len(open_tasks) > 5 else ""
        raise FinancialError(
            409,
            f"{len(open_tasks)} competitive or direct-assign task(s) have no award yet: {names}{more}. "
            "Confirm them to mark bidding complete anyway.",
        )
    result = call_rpc(
        db, "fn_complete_bidding",
        {"p_project_id": project_id, "p_actor": actor_id, "p_note": note},
        "Bidding could not be marked complete.",
    ) or {}
    result["open_tasks"] = open_tasks
    return result


def reopen_bidding(db: Client, *, project_id: str, actor_id: str) -> dict:
    _project(db, project_id)
    return call_rpc(
        db, "fn_reopen_bidding", {"p_project_id": project_id, "p_actor": actor_id},
        "Bidding could not be reopened.",
    ) or {}


# ── Overview (the contingency panel) ────────────────────────────────────────


def overview(db: Client, project_id: str, user: dict) -> dict:
    project = _project(db, project_id)
    settings = get_settings(db)
    snap = snapshot(db, project, settings)
    status = project.get("budget_status") or "none"
    ledger = build_ledger(db, project_id) if status == "baselined" else {
        "entries": [], "buckets": [], "total_in": "0.00", "total_out": "0.00",
    }
    top_ups = _top_up_rows(db, project_id)

    initial = next((b for b in ledger["buckets"] if b["kind"] == "initial"), None)
    approved_top_ups = sum(
        (_d(t["approved_amount"]) for t in top_ups if t["status"] == "approved"), Decimal("0")
    )

    alert = None
    alerts = (
        db.table("financial_alerts").select("id, severity, status, message, contingency_left_pct, created_at")
        .eq("project_id", project_id).eq("alert_type", "bidding_checkpoint")
        .order("created_at", desc=True).limit(1).execute()
    ).data or []
    if alerts and alerts[0]["status"] == "open":
        alert = alerts[0]

    completed_by = _users(db, {str(project.get("bidding_completed_by") or "")})
    completed = bool(project.get("bidding_completed_at"))
    executive = is_executive(user)
    return {
        "project_id": project_id,
        "budget_status": status,
        **snap,
        "starting_amount": initial["starting_amount"] if initial else None,
        "top_ups_approved_total": _money(approved_top_ups),
        "total_in": ledger["total_in"],
        "total_out": ledger["total_out"],
        "buckets": ledger["buckets"],
        "top_ups": top_ups,
        "pending_top_ups": [t for t in top_ups if t["status"] == "pending"],
        "bidding": {
            "completed_at": project.get("bidding_completed_at"),
            "completed_by_name": _name(completed_by, project.get("bidding_completed_by")),
            "left_percent": str(project["bidding_contingency_left_pct"])
            if project.get("bidding_contingency_left_pct") is not None else None,
            "note": project.get("bidding_completion_note"),
            "outcome": outcome_for(
                str(project["bidding_contingency_left_pct"])
                if project.get("bidding_contingency_left_pct") is not None else None,
                settings,
            ) if completed else None,
            "alert": alert,
        },
        "permissions": {
            "set_percent": user.get("role") == "admin" and status != "baselined",
            "request_top_up": user_has_any_role(user, "project_manager") and status == "baselined",
            "decide_top_up": executive and status == "baselined",
            "complete_bidding": can_manage_bidding(user) and status == "baselined" and not completed,
            "reopen_bidding": user.get("role") == "admin" and completed,
            "is_executive": executive,
        },
    }
