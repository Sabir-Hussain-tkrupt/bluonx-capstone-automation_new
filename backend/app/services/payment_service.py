"""Payment approvals (Phase 6 · Tasks 6.1, 6.3, 6.7).

The rules engine (payment_rules) decides each step; the stored procedures
record it and re-check the hard rules. Notifications, the PO PDF and the
finance hand-off run after commit in payment_notifications.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from app.services import payment_rules as rules
from app.services.budget_service import _ensure_editable, get_line, get_project
from app.services.contingency_service import get_settings
from app.services.financial_errors import FinancialError, call_rpc, first, money, to_financial_error

_PAGE = 500
_STEP_LABEL = {"field": "Confirm work and approve", "manager": "Approve (second approval)",
               "executive": "Approve (executive)"}
EVENT_LABELS = {
    "requested": "Payment requested",
    "work_confirmed": "Work confirmed complete",
    "routed_to_manager": "Sent to a manager",
    "manager_approved": "Manager approved",
    "routed_to_executive": "Sent to an executive",
    "executive_approved": "Executive approved",
    "approved": "Approved for payment",
    "rejected": "Rejected, back to the field manager",
    "resubmitted": "Resubmitted",
    "cancelled": "Withdrawn",
    "sent_to_finance": "Sent to finance",
    "handoff_failed": "Hand-off email failed",
}


def _d(v: Any) -> Decimal:
    return Decimal(str(v)) if v not in (None, "") else Decimal("0")


# ── Facts for the rules ─────────────────────────────────────────────────────


def policy(db: Client) -> rules.Policy:
    s = get_settings(db)
    threshold = s.get("executive_approval_threshold")
    return rules.Policy(
        default_limit=_d(s.get("default_field_approval_limit") or 5000),
        # "off" / null = no executive level. The database reads it the same way.
        executive_threshold=_d(threshold) if isinstance(threshold, (int, float)) and not isinstance(threshold, bool) else None,
    )


def approver(db: Client, user: dict) -> rules.Approver:
    resp = db.table("users").select("approval_limit, is_employee").eq("id", str(user["user_id"])).maybe_single().execute()
    row = (resp.data if resp else None) or {}
    roles = set(user.get("roles") or []) | {user.get("role")}
    limit = row.get("approval_limit")
    return rules.Approver(
        id=str(user["user_id"]), roles=frozenset(r for r in roles if r),
        is_employee=row.get("is_employee", user.get("is_employee", True)) is not False,
        approval_limit=_d(limit) if limit is not None else None,
    )


def facts(row: dict) -> rules.Payment:
    return rules.Payment(
        status=row["status"], gross=_d(row.get("gross_amount") or row.get("amount")),
        field_approved_by=_s(row.get("field_approved_by")), manager_approved_by=_s(row.get("manager_approved_by")),
        executive_approved_by=_s(row.get("executive_approved_by")),
        confirmed_by_external=bool(row.get("confirmed_by_external")), routed_to=_s(row.get("routed_to_user_id")),
        variance_created_by=_s(row.get("variance_created_by")),
    )


def _s(v: Any) -> str | None:
    return str(v) if v else None


def permissions(row: dict, actor: rules.Approver, pol: rules.Policy) -> dict:
    p = facts(row)
    d = rules.decide(p, actor, pol)
    open_ = row["status"] in rules.OPEN
    simple = not row.get("internal_invoice_id") and not row.get("variance_id")
    return {
        "can_approve": open_ and d.allowed,
        "approve_label": _STEP_LABEL.get(d.step or "", "Approve"),
        "needs_work_confirmation": d.step == "field",
        "approve_blocked_reason": None if d.allowed or not open_ else d.reason,
        "can_reject": rules.can_reject(p, actor),
        "can_resubmit": row["status"] == "rejected" and simple and bool(actor.roles & rules.CONFIRM_ROLES),
        "can_cancel": row["status"] in (*rules.OPEN, "rejected") and simple
        and (actor.id == str(row.get("requested_by")) or bool(actor.roles & {"project_manager", "admin"})),
        "executive_needed": rules.executive_needed(p, pol),
    }


# ── Reads ───────────────────────────────────────────────────────────────────


def get_payment(db: Client, payment_id: str) -> dict:
    resp = db.table("v_payment_approvals").select("*").eq("id", payment_id).maybe_single().execute()
    if not resp or not resp.data:
        raise FinancialError(404, "Payment approval not found")
    return resp.data


def list_payments(db: Client, user: dict, *, scope: str, project_id: str | None = None) -> list[dict]:
    statuses = {
        "queue": list(rules.OPEN), "pending": list(rules.OPEN), "rejected": ["rejected"],
        "sent": ["approved", "sent_to_finance"], "all": None,
    }[scope]
    rows: list[dict] = []
    while True:
        q = db.table("v_payment_approvals").select("*")
        if statuses:
            q = q.in_("status", statuses)
        if project_id:
            q = q.eq("project_id", project_id)
        batch = (q.order("created_at", desc=True).order("id").range(len(rows), len(rows) + _PAGE - 1).execute()).data or []
        rows.extend(batch)
        if len(batch) < _PAGE:
            break
    actor, pol = approver(db, user), policy(db)
    out = [{**r, "permissions": permissions(r, actor, pol)} for r in rows]
    if scope == "queue":
        out = [r for r in out if r["permissions"]["can_approve"]]
    return out


def detail(db: Client, payment_id: str, user: dict) -> dict:
    row = get_payment(db, payment_id)
    events = (
        db.table("payment_approval_events").select("*").eq("payment_approval_id", payment_id).order("event_no").execute()
    ).data or []
    ids = list({str(e["actor_user_id"]) for e in events if e.get("actor_user_id")})
    users = db.table("users").select("id, full_name, email").in_("id", ids).execute().data or [] if ids else []
    names = {str(u["id"]): u.get("full_name") or u.get("email") for u in users}
    return {
        **row,
        "permissions": permissions(row, approver(db, user), policy(db)),
        "history": [
            {**e, "label": EVENT_LABELS.get(e["event_type"], e["event_type"]),
             "actor_name": names.get(str(e.get("actor_user_id"))) if e.get("actor_user_id") else "System"}
            for e in events
        ],
    }


def line_options(db: Client, line_id: str, user: dict) -> dict:
    """What can be paid on a bid line now: amounts, retainage, kinds."""
    line = get_line(db, line_id)
    reqs = (
        db.table("v_payment_approvals").select("*").eq("budget_line_id", line_id)
        .order("created_at", desc=True).execute()
    ).data or []
    live = [r for r in reqs if r["status"] not in ("rejected", "cancelled")]
    total = _d(line.get("committed_amount") if line["line_type"] == "bid_activity" else line.get("budget_amount"))
    used = sum((_d(r["gross_amount"]) for r in live if r["payment_kind"] != "retainage_release"), Decimal("0"))
    held = sum((_d(r["retainage_amount"]) for r in live if r["payment_kind"] != "retainage_release"), Decimal("0"))
    released = sum((_d(r["amount"]) for r in live if r["payment_kind"] == "retainage_release"), Decimal("0"))
    contract = (reqs[0] if reqs else {}) or {}
    retainage = contract.get("retainage_percent")
    if retainage is None and line.get("award_id"):
        rows = (
            db.table("contracts").select("retainage_percent, contract_number, payment_terms_days")
            .eq("award_id", line["award_id"]).neq("status", "terminated").limit(1).execute()
        ).data or []
        contract = rows[0] if rows else {}
        retainage = contract.get("retainage_percent")
    open_ = next((r for r in reqs if r["status"] in rules.OPEN), None)
    actor, pol = approver(db, user), policy(db)
    return {
        "line_id": line_id,
        "line_name": line["name"],
        "line_type": line["line_type"],
        "has_award": bool(line.get("award_id")),
        "total": money(total),
        "requested": money(used),
        "remaining": money(max(total - used, Decimal("0"))),
        "retainage_percent": None if retainage is None else str(retainage),
        "retainage_held": money(held - released),
        "contract_number": contract.get("contract_number"),
        "open_request": {**open_, "permissions": permissions(open_, actor, pol)} if open_ else None,
        "history": [{**r, "permissions": permissions(r, actor, pol)} for r in reqs],
        "can_confirm": bool(actor.roles & rules.CONFIRM_ROLES),
    }


# ── Writes ──────────────────────────────────────────────────────────────────


def _route(db: Client, row: dict, actor_id: str) -> str | None:
    """Reports-to manager of the person who gave the first approval, then the
    project's manager. A delegate stands in for an away manager; the backup for
    an inactive one."""
    first_by = str(row.get("field_approved_by") or actor_id)
    me = db.table("users").select("reports_to").eq("id", first_by).maybe_single().execute()
    project = db.table("projects").select("manager_id").eq("id", row["project_id"]).maybe_single().execute()
    managers = [((me.data if me else None) or {}).get("reports_to"),
                ((project.data if project else None) or {}).get("manager_id")]
    ids = [str(m) for m in managers if m]
    if not ids:
        return None
    people = {
        str(u["id"]): u for u in (
            db.table("users").select("id, is_active, deleted_at, backup_approver_id").in_("id", ids).execute()
        ).data or []
    }
    now = datetime.now(timezone.utc).isoformat()
    delegations = (
        db.table("approval_delegations").select("delegator_user_id, delegate_user_id")
        .in_("delegator_user_id", ids).is_("revoked_at", "null").lte("starts_at", now).gt("ends_at", now).execute()
    ).data or []
    delegate = {str(d["delegator_user_id"]): str(d["delegate_user_id"]) for d in delegations}
    candidates = []
    for m in ids:
        u = people.get(m) or {}
        candidates.append((m, delegate.get(m), _s(u.get("backup_approver_id")),
                           bool(u.get("is_active")) and not u.get("deleted_at")))
    exclude = {first_by, actor_id} | ({str(row["variance_created_by"])} if row.get("variance_created_by") else set())
    return rules.pick_manager(candidates, exclude)


def _guard(db: Client, row: dict) -> None:
    _ensure_editable(get_project(db, row["project_id"]))


def approve(db: Client, *, payment_id: str, user: dict, note: str | None, work_confirmed: bool) -> dict:
    row = get_payment(db, payment_id)
    _guard(db, row)
    d = rules.decide(facts(row), approver(db, user), policy(db))
    if not d.allowed:
        raise FinancialError(403, d.reason)
    if d.step == "field" and not work_confirmed:
        raise FinancialError(422, "Confirm the work is complete before approving.")
    routed = _route(db, {**row, "field_approved_by": row.get("field_approved_by") or user["user_id"]},
                    str(user["user_id"])) if d.route_to_manager else None
    result = call_rpc(
        db, "fn_payment_approval_step",
        {
            "p_id": payment_id, "p_actor": str(user["user_id"]), "p_expected_status": row["status"],
            "p_step": d.step, "p_next_status": d.next_status, "p_routed_to": routed,
            "p_note": (note or "").strip() or None, "p_work_confirmed": bool(work_confirmed),
        },
        "The approval could not be saved.",
    )
    return {"payment": get_payment(db, payment_id), "result": first(result) or {}}


def request(db: Client, *, line_id: str, user: dict, kind: str, percent: Decimal | None, note: str | None,
            confirm_now: bool) -> dict:
    line = get_line(db, line_id)
    _ensure_editable(get_project(db, line["project_id"]))
    created = first(call_rpc(
        db, "fn_request_payment",
        {"p_line_id": line_id, "p_actor": str(user["user_id"]), "p_kind": kind,
         "p_percent": money(percent), "p_note": (note or "").strip() or None},
        "The payment could not be requested.",
    ))
    if not created:
        raise FinancialError(500, "The payment could not be requested.")
    if confirm_now:
        return approve(db, payment_id=str(created["id"]), user=user, note=note, work_confirmed=True)
    return {"payment": get_payment(db, str(created["id"])), "result": {}}


def for_variance(db: Client, *, variance_id: str, user: dict, note: str | None, work_confirmed: bool) -> dict:
    """Variance "Approve for payment": the variance's own request, through the same engine."""
    v = db.table("v_variances").select("budget_line_id, project_id").eq("id", variance_id).maybe_single().execute()
    if not v or not v.data:
        raise FinancialError(404, "Variance not found")
    line_id = str(v.data["budget_line_id"])
    open_ = (
        db.table("payment_approvals").select("id").eq("budget_line_id", line_id)
        .in_("status", list(rules.OPEN)).limit(1).execute()
    ).data or []
    if open_:
        return approve(db, payment_id=str(open_[0]["id"]), user=user, note=note, work_confirmed=work_confirmed)
    return request(db, line_id=line_id, user=user, kind="full", percent=None, note=note, confirm_now=True)


def _simple(db: Client, fn: str, payment_id: str, user: dict, text_key: str, text: str | None) -> dict:
    row = get_payment(db, payment_id)
    _guard(db, row)
    call_rpc(db, fn, {"p_id": payment_id, "p_actor": str(user["user_id"]), text_key: (text or "").strip() or None},
             "The payment could not be updated.")
    return row


def reject(db: Client, *, payment_id: str, user: dict, reason: str) -> dict:
    _simple(db, "fn_reject_payment", payment_id, user, "p_reason", reason)
    return get_payment(db, payment_id)


def resubmit(db: Client, *, payment_id: str, user: dict, note: str | None) -> dict:
    new = first(call_rpc(
        db, "fn_resubmit_payment",
        {"p_id": payment_id, "p_actor": str(user["user_id"]), "p_note": (note or "").strip() or None},
        "The payment could not be resubmitted.",
    ))
    return get_payment(db, str(new["id"])) if new else get_payment(db, payment_id)


def cancel(db: Client, *, payment_id: str, user: dict, note: str | None) -> dict:
    _simple(db, "fn_cancel_payment", payment_id, user, "p_note", note)
    return get_payment(db, payment_id)


# ── Approver settings per user (admin) ──────────────────────────────────────


def approver_settings(db: Client) -> list[dict]:
    users = (
        db.table("users").select("id, full_name, email, role, is_active, is_employee, approval_limit, reports_to, "
                                 "backup_approver_id, deleted_at").is_("deleted_at", "null").order("full_name").execute()
    ).data or []
    roles = (db.table("user_roles").select("user_id, role").is_("revoked_at", "null").execute()).data or []
    held: dict[str, set[str]] = {}
    for r in roles:
        held.setdefault(str(r["user_id"]), set()).add(r["role"])
    now = datetime.now(timezone.utc).isoformat()
    away = (
        db.table("approval_delegations").select("delegator_user_id, delegate_user_id, ends_at")
        .is_("revoked_at", "null").gt("ends_at", now).lte("starts_at", now).execute()
    ).data or []
    away_by = {str(a["delegator_user_id"]): a for a in away}
    out = []
    for u in users:
        uid = str(u["id"])
        out.append({
            "id": uid, "name": u.get("full_name") or u.get("email"), "is_active": u.get("is_active"),
            "roles": sorted(held.get(uid, set()) | {u["role"]}), "is_employee": u.get("is_employee") is not False,
            "approval_limit": u.get("approval_limit"), "reports_to": u.get("reports_to"),
            "backup_approver_id": u.get("backup_approver_id"),
            "away_until": (away_by.get(uid) or {}).get("ends_at"),
        })
    return out


def update_approver_settings(db: Client, *, user_id: str, changes: dict, actor_id: str) -> None:
    update: dict[str, Any] = {}
    for key in ("reports_to", "backup_approver_id"):
        if key in changes:
            value = str(changes[key]) if changes[key] else None
            if value == user_id:
                raise FinancialError(422, "A person cannot be their own manager or backup.")
            update[key] = value
    if "approval_limit" in changes:
        update["approval_limit"] = money(changes["approval_limit"])
    try:
        if update:
            db.table("users").update(update).eq("id", user_id).execute()
        if "away_until" in changes:
            now = datetime.now(timezone.utc)
            db.table("approval_delegations").update({"revoked_at": now.isoformat()}).eq(
                "delegator_user_id", user_id).is_("revoked_at", "null").gt("ends_at", now.isoformat()).execute()
            until = changes["away_until"]
            if until:
                if until <= now:
                    raise FinancialError(422, "The away date must be in the future.")
                row = db.table("users").select("backup_approver_id").eq("id", user_id).maybe_single().execute()
                backup = ((row.data if row else None) or {}).get("backup_approver_id")
                if not backup:
                    raise FinancialError(422, "Choose a backup approver first: approvals go to them while away.")
                db.table("approval_delegations").insert({
                    "delegator_user_id": user_id, "delegate_user_id": str(backup), "starts_at": now.isoformat(),
                    "ends_at": until.isoformat(), "reason": "Away", "created_by": actor_id,
                }).execute()
    except APIError as exc:
        raise to_financial_error(exc, "The approval settings could not be saved.") from exc
