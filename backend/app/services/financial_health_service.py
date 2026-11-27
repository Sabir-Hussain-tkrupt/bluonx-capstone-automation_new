"""Contingency health: recalculation, alerts, decisions (Phase 5 · Module 5).

`after_change` is called after every spend, variance, contingency or milestone
change: it recalculates (financial_health), syncs the alerts in the database and
sends what is new. It never raises: the change it follows has already committed.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from postgrest.exceptions import APIError
from starlette.concurrency import run_in_threadpool
from supabase import Client

from app.core.auth import user_has_any_role
from app.services import financial_health as fh
from app.services.budget_service import _ensure_editable, get_project
from app.services.financial_errors import FinancialError, call_rpc, first, to_financial_error

logger = logging.getLogger(__name__)

MANAGER_ROLES = ("project_manager", "executive")
_PAGE = 500
_background: set[asyncio.Task] = set()


def can_manage(user: dict) -> bool:
    return user_has_any_role(user, *MANAGER_ROLES)


# ── Recalculation ───────────────────────────────────────────────────────────


def inputs(db: Client, project_id: str) -> dict:
    row = call_rpc(db, "fn_project_health_inputs", {"p_project_id": str(project_id)},
                   "The project health could not be calculated.")
    row = first(row)
    if not row:
        raise FinancialError(404, "Project not found")
    return row


def recalculate(db: Client, project_id: str) -> list[str]:
    """Recalculate and sync the alerts. Returns the ids of new alerts."""
    data = fh.from_row(inputs(db, project_id))
    result = fh.calculate(data)
    return call_rpc(
        db, "fn_sync_financial_alerts",
        {"p_project_id": str(project_id), "p_checks": fh.checks_payload(data, result)},
        "The financial alerts could not be updated.",
    ) or []


async def after_change(db: Client, project_id: Any, email_service: Any = None) -> None:
    try:
        opened = await run_in_threadpool(recalculate, db, str(project_id))
        if opened:
            from app.services import financial_alert_notifications as notify

            await notify.send_new(db, email_service or notify.email_service(db), alert_ids=opened)
    except Exception:  # noqa: BLE001 - the daily sweep repeats both steps
        logger.exception("Financial health: recalculation failed for project %s", project_id)


def after_change_soon(db: Client, project_id: Any) -> None:
    """Same, for synchronous code (award / DocuSign hooks, milestone service),
    whether it runs on the event loop or in a worker thread."""
    if not project_id:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        threading.Thread(
            target=lambda: asyncio.run(after_change(db, project_id)), name="financial-health", daemon=True,
        ).start()
        return
    task = loop.create_task(after_change(db, project_id))
    _background.add(task)
    task.add_done_callback(_background.discard)


def after_task_change(db: Client, task_id: Any) -> None:
    """Milestone progress changed on this task. Never raises."""
    try:
        resp = db.table("tasks").select("project_id").eq("id", str(task_id)).maybe_single().execute()
        row = resp.data if resp else None
        if isinstance(row, dict):
            after_change_soon(db, row.get("project_id"))
    except Exception:  # noqa: BLE001
        logger.exception("Financial health: no project for task %s", task_id)


def after_milestone_change(db: Client, milestone_id: Any) -> None:
    try:
        resp = db.table("milestones").select("task_id").eq("id", str(milestone_id)).maybe_single().execute()
        row = resp.data if resp else None
        if isinstance(row, dict):
            after_task_change(db, row.get("task_id"))
    except Exception:  # noqa: BLE001
        logger.exception("Financial health: no task for milestone %s", milestone_id)


# ── Panel ───────────────────────────────────────────────────────────────────


def _team(db: Client) -> list[dict]:
    """Active people with the roles that matter here."""
    grants = (
        db.table("user_roles").select("user_id, role").is_("revoked_at", "null")
        .in_("role", ["field_manager", "project_manager", "executive", "admin"]).execute()
    ).data or []
    roles: dict[str, list[str]] = {}
    for g in grants:
        roles.setdefault(str(g["user_id"]), []).append(g["role"])
    if not roles:
        return []
    users = (
        db.table("users").select("id, full_name, email, is_active, deleted_at").in_("id", list(roles)).execute()
    ).data or []
    out = [
        {"id": str(u["id"]), "name": u.get("full_name") or u.get("email"), "roles": sorted(set(roles[str(u["id"])]))}
        for u in users if u.get("is_active") and not u.get("deleted_at")
    ]
    return sorted(out, key=lambda u: (u["name"] or "").lower())


def overview(db: Client, project_id: str, user: dict) -> dict:
    row = inputs(db, project_id)
    data = fh.from_row(row)
    r = fh.calculate(data)
    alerts = list_alerts(db, project_id=project_id, live_only=True)
    manager = can_manage(user)
    return {
        "project_id": project_id,
        "project_status": row["status"],
        "live": data.live,
        "contingency": str(fh.cents(data.contingency)),
        "contingency_base": None if data.contingency_base is None else str(fh.cents(data.contingency_base)),
        "groundbreaking_at": row.get("groundbreaking_at"),
        "contingency_left_pct": fh.pct_out(r.contingency_left_pct),
        "work_left_dollars_pct": fh.pct_out(r.work_left_dollars_pct),
        "work_left_physical_pct": fh.pct_out(r.work_left_physical_pct),
        "work_left_pct": fh.pct_out(r.work_left_pct),
        "work_left_basis": r.work_left_basis,
        "milestones_total": data.milestones_total,
        "milestones_completed": data.milestones_completed,
        "total_budget": str(fh.cents(data.total_budget)),
        "spent": str(fh.cents(r.spent)),
        "spent_committed": str(fh.cents(r.committed)),
        "spent_approved": str(fh.cents(r.approved)),
        "spent_sent": str(fh.cents(r.sent)),
        "spent_land": str(fh.cents(r.land_closed)),
        "reserve": None if data.reserve is None else str(fh.cents(data.reserve)),
        "near_zero_percent": str(data.near_zero_percent),
        "manager_id": row.get("manager_id"),
        "field_manager_id": row.get("field_manager_id"),
        "team": _team(db),
        "alerts": alerts,
        "financial_hold": any(a["status"] == "on_hold" for a in alerts),
        "permissions": {
            "manage": manager and not row.get("archived"),
            "record_groundbreaking": manager and data.live and not row.get("groundbreaking_at"),
        },
    }


def update_setup(db: Client, *, project_id: str, changes: dict, actor_id: str) -> None:
    project = get_project(db, project_id)
    _ensure_editable(project)
    update: dict[str, Any] = {}
    for key, role in (("manager_id", MANAGER_ROLES + ("admin",)), ("field_manager_id", ("field_manager",))):
        if key not in changes:
            continue
        value = str(changes[key]) if changes[key] else None
        if value and value != str(project.get(key) or ""):
            if not any(m["id"] == value and set(m["roles"]) & set(role) for m in _team(db)):
                raise FinancialError(422, "The selected person does not hold the required role.")
        update[key] = value
    if "reserve" in changes:
        update["long_tail_reserve_amount"] = None if changes["reserve"] is None else str(changes["reserve"])
        update["long_tail_reserve_updated_at"] = "now()"
        update["long_tail_reserve_updated_by"] = str(actor_id)
    if not update:
        return
    try:
        db.table("projects").update(update).eq("id", project_id).execute()
    except APIError as exc:
        raise to_financial_error(exc, "The health setup could not be saved.") from exc


def record_groundbreaking(db: Client, *, project_id: str, actor_id: str) -> None:
    _ensure_editable(get_project(db, project_id))
    call_rpc(db, "fn_record_groundbreaking", {"p_project_id": project_id, "p_actor": str(actor_id)},
             "Groundbreaking could not be recorded.")


# ── Alerts and decisions ────────────────────────────────────────────────────


def list_alerts(
    db: Client, *, project_id: str | None = None, status: str | None = None, live_only: bool = False,
) -> list[dict]:
    rows: list[dict] = []
    while True:
        q = db.table("v_financial_alerts").select("*").in_("alert_type", list(fh.ALERT_TYPES))
        if project_id:
            q = q.eq("project_id", project_id)
        if status:
            q = q.eq("status", status)
        if live_only:
            q = q.in_("status", ["open", "acknowledged", "proceed_approved", "on_hold"])
        batch = (
            q.order("created_at", desc=True).order("id").range(len(rows), len(rows) + _PAGE - 1).execute()
        ).data or []
        rows.extend(batch)
        if len(batch) < _PAGE:
            return rows


def get_alert(db: Client, alert_id: str) -> dict:
    resp = db.table("v_financial_alerts").select("*").eq("id", alert_id).maybe_single().execute()
    if not resp or not resp.data or resp.data["alert_type"] not in fh.ALERT_TYPES:
        raise FinancialError(404, "Alert not found")
    return resp.data


def alert_detail(db: Client, alert_id: str, user: dict) -> dict:
    alert = get_alert(db, alert_id)
    health = overview(db, str(alert["project_id"]), user)
    uid = str(user["user_id"])
    team = health["team"]
    field_manager = str(alert.get("field_manager_id") or "")
    options = [
        m for m in team if m["id"] != uid and ("field_manager" in m["roles"] or m["id"] == field_manager)
    ]
    manage = health["permissions"]["manage"]
    return {
        **alert,
        "health": health,
        "field_managers": options,
        "permissions": {
            "can_decide": manage and health["live"] and alert["status"] in ("open", "acknowledged"),
            "can_lift": manage and health["financial_hold"],
        },
    }


def decide(
    db: Client, *, alert_id: str, decision: str, reason: str, discussed_with: str, notes: str, actor_id: str,
) -> dict:
    alert = get_alert(db, alert_id)
    _ensure_editable(get_project(db, str(alert["project_id"])))
    call_rpc(
        db, "fn_decide_financial_alert",
        {
            "p_alert_id": alert_id, "p_actor": str(actor_id), "p_decision": decision, "p_reason": reason,
            "p_discussed_with": discussed_with, "p_notes": notes,
        },
        "The decision could not be saved.",
    )
    return get_alert(db, alert_id)


def lift_hold(db: Client, *, project_id: str, reason: str, actor_id: str) -> None:
    _ensure_editable(get_project(db, project_id))
    call_rpc(
        db, "fn_lift_financial_hold",
        {"p_project_id": project_id, "p_actor": str(actor_id), "p_reason": reason},
        "The hold could not be lifted.",
    )
