"""Notifications for variances (Phase 4).

  created / edited      → the project's manager and field manager, else every
                          project manager: in-app
  routed to a manager   → that manager, or every project manager: in-app + email
  approved / rejected   → the person who created it: in-app + email

Called after the change has committed; never raises.
"""

from __future__ import annotations

import logging

from supabase import Client

from app.services.contingency_notifications import _email, _fmt, _notify, _role_users
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


def _users(db: Client, ids: list) -> list[dict]:
    wanted = list({str(i) for i in ids if i})
    if not wanted:
        return []
    rows = (
        db.table("users").select("id, email, full_name, is_active, deleted_at").in_("id", wanted).execute()
    ).data or []
    return [u for u in rows if u.get("is_active") and not u.get("deleted_at")]


def _others(people: list[dict], variance: dict, actor: dict) -> list[dict]:
    skip = {str(actor["user_id"]), str(variance["created_by"])}
    return [u for u in people if str(u["id"]) not in skip]


def _who(user: dict) -> str:
    return user.get("full_name") or user.get("email") or "Someone"


def _summary(v: dict) -> str:
    return f"{_fmt(v['amount'])} under \"{v['parent_line_name']}\": {v['description']}"


async def submitted(db: Client, *, variance: dict, actor: dict) -> None:
    try:
        project = (
            db.table("projects").select("manager_id, field_manager_id")
            .eq("id", variance["project_id"]).maybe_single().execute()
        )
        p = (project.data if project else None) or {}
        people = _others(_users(db, [p.get("manager_id"), p.get("field_manager_id")]), variance, actor)
        if not people:  # nobody assigned, or the assigned person created it
            people = _others(_role_users(db, "project_manager"), variance, actor)
        _notify(
            db, people, ntype="variance_pending_approval",
            title=f"Variance to approve: {variance['project_name']}",
            message=f"{_who(actor)} submitted {_summary(variance)}", project_id=str(variance["project_id"]),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Variance: submit notification failed for %s", variance.get("id"))


async def decided(db: Client, email_service: EmailService, *, variance: dict, actor: dict) -> None:
    """After approve / reject: ask the manager, or tell the creator the outcome."""
    try:
        project_id = str(variance["project_id"])
        if variance["status"] == "pending_approval":
            routed = variance.get("routed_to_user_id")
            people = _others(_users(db, [routed]) if routed else _role_users(db, "project_manager"), variance, actor)
            title = f"Variance needs your approval: {variance['project_name']}"
            message = (
                f"{_who(actor)} approved {_summary(variance)} "
                "(above their approval limit, so a manager must approve it too)."
            )
            ntype, etype = "variance_pending_approval", "payment_approval_request"
        else:
            people = _users(db, [variance["created_by"]])
            approved = variance["status"] == "approved"
            verdict = "approved for payment" if approved else "rejected"
            title = f"Variance {verdict}: {variance['project_name']}"
            message = f"{_who(actor)} {verdict}: {_summary(variance)}"
            if not approved:
                message += f" Reason: {variance.get('rejection_reason')}. Edit it to resubmit, or cancel it."
            ntype = "variance_approved" if approved else "variance_rejected"
            etype = "payment_approved" if approved else "payment_rejected"
        _notify(db, people, ntype=ntype, title=title, message=message, project_id=project_id)
        await _email(
            email_service, [u["email"] for u in people if u.get("email")], subject=title, lines=[message],
            project_id=project_id, email_type=etype,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Variance: decision notification failed for %s", variance.get("id"))
