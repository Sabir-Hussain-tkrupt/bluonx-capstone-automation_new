"""Notifications for the contingency engine (Phase 3).

  top-up requested      → executives: in-app + email
  top-up decided        → requester: in-app; when approved, finance + sales
                          (finance role, finance_emails, sales_emails): email
  bidding checkpoint    → far below target: executives + finance: in-app + email

Every function is called AFTER the money change has committed and never
raises: a failed email must not undo or fail the financial action. Failures are
logged with the ids so they can be re-sent by hand.
"""

from __future__ import annotations

import html
import logging
from decimal import Decimal
from typing import Any

from supabase import Client

from app.core.config import settings
from app.services.contingency_service import get_settings
from app.services.email_service import EmailService
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)


def _fmt(amount: Any) -> str:
    try:
        return f"${Decimal(str(amount)):,.2f}"
    except Exception:  # noqa: BLE001 - formatting only
        return str(amount)


def _project_link(project_id: str) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/projects/{project_id}?tab=budget"


def _role_users(db: Client, role: str) -> list[dict]:
    rows = (
        db.table("user_roles").select("user_id")
        .eq("role", role).is_("revoked_at", "null").execute()
    ).data or []
    ids = list({str(r["user_id"]) for r in rows})
    if not ids:
        return []
    users = (
        db.table("users").select("id, email, full_name, is_active, deleted_at")
        .in_("id", ids).execute()
    ).data or []
    return [u for u in users if u.get("is_active") and not u.get("deleted_at")]


def _project_name(db: Client, project_id: str) -> str:
    resp = db.table("projects").select("name").eq("id", project_id).maybe_single().execute()
    return (resp.data or {}).get("name", "Project") if resp else "Project"


def _notify(db: Client, users: list[dict], *, ntype: str, title: str, message: str, project_id: str) -> None:
    for u in users:
        try:
            create_notification(
                db, user_id=u["id"], notification_type=ntype, title=title, message=message,
                reference_type="projects", reference_id=project_id, dedupe=False,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Contingency: in-app notification %s for user %s failed", ntype, u.get("id"))


async def _email(
    email_service: EmailService, recipients: list[str], *, subject: str, lines: list[str],
    project_id: str, email_type: str,
) -> None:
    link = _project_link(project_id)
    body_html = "".join(f"<p>{html.escape(line)}</p>" for line in lines)
    body_html += f'<p><a href="{html.escape(link)}">Open the project budget</a></p>'
    body_text = "\n\n".join(lines) + f"\n\nOpen the project budget: {link}"
    seen: set[str] = set()
    for address in recipients:
        key = address.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            await email_service.send_email(
                to_email=address.strip(), subject=subject, html_body=body_html, plain_text_body=body_text,
                email_type=email_type, recipient_type="user",
                reference_type="projects", reference_id=project_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Contingency: email %s to %s failed (project %s)", email_type, address, project_id)


def _setting_emails(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str) and "@" in v]
    return []


# ── Top-up requested ────────────────────────────────────────────────────────


async def top_up_requested(db: Client, email_service: EmailService, *, bucket: dict, requester: dict) -> None:
    try:
        project_id = str(bucket["project_id"])
        name = _project_name(db, project_id)
        amount = _fmt(bucket["requested_amount"])
        who = requester.get("full_name") or requester.get("email") or "A project manager"
        title = f"Contingency top-up requested: {name}"
        message = f"{who} asked for {amount} more contingency. Reason: {bucket['reason']}"
        executives = _role_users(db, "executive")
        _notify(db, executives, ntype="top_up_requested", title=title, message=message, project_id=project_id)
        await _email(
            email_service, [u["email"] for u in executives if u.get("email")],
            subject=title,
            lines=[
                f"{who} requested a contingency top-up of {amount} on {name}.",
                f"Reason: {bucket['reason']}",
                "Only an executive can approve or reject it. The approved amount is added to the project's "
                "contingency and to its total budget.",
            ],
            project_id=project_id, email_type="contingency_top_up",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Contingency: top-up request notifications failed for %s", bucket.get("id"))


# ── Top-up decided ──────────────────────────────────────────────────────────


async def top_up_decided(db: Client, email_service: EmailService, *, bucket: dict, approver: dict) -> None:
    try:
        project_id = str(bucket["project_id"])
        name = _project_name(db, project_id)
        who = approver.get("full_name") or approver.get("email") or "An executive"
        approved = bucket.get("status") == "approved"
        amount = _fmt(bucket.get("approved_amount") or bucket["requested_amount"])
        note = bucket.get("decision_note")

        requester = (
            db.table("users").select("id, email, full_name, is_active, deleted_at")
            .eq("id", str(bucket["requested_by"])).maybe_single().execute()
        )
        if requester and requester.data:
            verdict = f"approved {amount}" if approved else "rejected"
            _notify(
                db, [requester.data], ntype="top_up_decided",
                title=f"Contingency top-up {'approved' if approved else 'rejected'}: {name}",
                message=f"{who} {verdict}.{f' Note: {note}' if note else ''}",
                project_id=project_id,
            )

        if not approved:
            return

        cfg = get_settings(db)
        finance_users = _role_users(db, "finance")
        recipients = (
            [u["email"] for u in finance_users if u.get("email")]
            + _setting_emails(cfg.get("finance_emails"))
            + _setting_emails(cfg.get("sales_emails"))
        )
        await _email(
            email_service, recipients,
            subject=f"Contingency top-up approved: {name} (+{amount})",
            lines=[
                f"{who} approved a contingency top-up of {amount} on {name}.",
                f"Reason: {bucket['reason']}" + (f" Decision note: {note}" if note else ""),
                f"The project's total budget is now {amount} higher. Please take this into account before home "
                "prices are set.",
            ],
            project_id=project_id, email_type="contingency_top_up",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Contingency: top-up decision notifications failed for %s", bucket.get("id"))


# ── Bidding checkpoint ──────────────────────────────────────────────────────


async def bidding_completed(
    db: Client, email_service: EmailService, *, project_id: str, result: dict, actor: dict,
) -> None:
    try:
        if result.get("outcome") != "escalated":
            return
        name = _project_name(db, project_id)
        who = actor.get("full_name") or actor.get("email") or "The project manager"
        left = result.get("left_percent")
        target = result.get("target_percent")
        contingency = _fmt(result.get("contingency"))
        title = f"Low contingency after bidding: {name} ({left}% left)"
        message = (
            f"{who} marked bidding complete with {contingency} contingency left, {left}% of the base "
            f"(target {target}%). Review before sale prices are set."
        )
        cfg = get_settings(db)
        people = _role_users(db, "executive") + _role_users(db, "finance")
        unique = list({u["id"]: u for u in people}.values())
        _notify(db, unique, ntype="bidding_checkpoint_alert", title=title, message=message, project_id=project_id)
        await _email(
            email_service,
            [u["email"] for u in unique if u.get("email")] + _setting_emails(cfg.get("finance_emails")),
            subject=title,
            lines=[
                message,
                f"Escalation threshold: {result.get('escalation_percent')}% of the contingency base. "
                "Consider a contingency top-up or a price review before sale prices are set.",
            ],
            project_id=project_id, email_type="contingency_escalation",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Contingency: bidding checkpoint notifications failed for project %s", project_id)
