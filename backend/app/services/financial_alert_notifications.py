"""Emails and in-app notifications for financial alerts (Phase 5 · Tasks 5.2, 5.5, 5.6).

  new alert      → project manager + field manager (else everyone with that
                   role) and the recipients for its severity: in-app + email
  critical alert → the executives as well
  undecided      → executives, `alert_escalation_days` after it opened (sweep)
  decision / lift → the same people, in-app; executives are emailed on a hold

Recipients per severity live in financial_settings.alert_recipients (emails or
user ids). Critical alerts also go to the urgent list.

Never raises: callers have already committed their change.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from starlette.concurrency import run_in_threadpool
from supabase import Client

from app.core.config import settings
from app.services import financial_health as fh
from app.services.contingency_notifications import _fmt, _role_users
from app.services.contingency_service import get_settings
from app.services.email_service import EmailService, create_email_provider
from app.services.notification_service import create_notification
from app.services.template_renderer import template_renderer
from app.services.variance_notifications import _users

logger = logging.getLogger(__name__)

# alert_type → (notification type, email template, email_log type, title)
_KINDS = {
    fh.HEALTH: ("contingency_health_alert", "contingency_health_alert", "contingency_alert", "Contingency health alert"),
    fh.NEAR_ZERO: ("contingency_urgent_alert", "contingency_urgent_alert", "contingency_alert", "Urgent: contingency nearly used up"),
    fh.NEGATIVE: ("contingency_urgent_alert", "contingency_urgent_alert", "contingency_alert", "Urgent: contingency is negative"),
    fh.RESERVE: ("long_tail_reserve_alert", "long_tail_reserve_alert", "long_tail_reserve_alert", "Long-tail reserve alert"),
}


def email_service(db: Client) -> EmailService:
    return EmailService(provider=create_email_provider(), db_client=db)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Who ─────────────────────────────────────────────────────────────────────


def _setting_people(db: Client, entries: Any) -> tuple[list[dict], list[str]]:
    """(app users, plain emails) from a recipients list of emails / user ids."""
    values = [str(v).strip() for v in entries or [] if str(v).strip()]
    emails = [v for v in values if "@" in v]
    users = _users(db, [v for v in values if "@" not in v])
    for address in emails:
        # ilike without wildcards = case-insensitive match.
        pattern = address.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        rows = (
            db.table("users").select("id, email, full_name, is_active, deleted_at").ilike("email", pattern).execute()
        ).data or []
        users += [u for u in rows if u.get("is_active") and not u.get("deleted_at")]
    return users, emails


def _recipients(db: Client, alert: dict) -> tuple[list[dict], list[str]]:
    managers = _users(db, [alert.get("manager_id")]) or _role_users(db, "project_manager")
    fields = _users(db, [alert.get("field_manager_id")]) or _role_users(db, "field_manager")
    configured = get_settings(db).get("alert_recipients") or {}
    entries = list(configured.get(alert["severity"]) or [])
    if alert["severity"] == "critical":
        entries += list(configured.get("urgent") or [])
    extra, emails = _setting_people(db, entries)
    people = managers + fields + extra
    if alert["severity"] == "critical":
        people += _role_users(db, "executive")
    return list({str(u["id"]): u for u in people}.values()), emails


# ── Sending ─────────────────────────────────────────────────────────────────


def _notify(db: Client, users: list[dict], alert: dict, *, ntype: str, title: str, message: str) -> None:
    for u in users:
        try:
            create_notification(
                db, user_id=u["id"], notification_type=ntype, title=title[:255], message=message,
                reference_type="financial_alerts", reference_id=alert["id"],
            )
        except Exception:  # noqa: BLE001
            logger.exception("Financial alert %s: in-app notification for %s failed", alert["id"], u.get("id"))


async def _email(
    service: EmailService, addresses: list[str], alert: dict, *, template: str, email_type: str, subject: str,
    extra: dict | None = None,
) -> None:
    context = {
        "project_name": alert["project_name"],
        "message": alert.get("message") or "",
        "contingency": _fmt(alert["contingency_remaining"]) if alert.get("contingency_remaining") is not None else None,
        "left_pct": alert.get("contingency_left_pct"),
        "work_left_pct": alert.get("work_left_pct"),
        "reserve": _fmt(alert["reserve_required"]) if alert.get("reserve_required") is not None else None,
        "link": f"{settings.FRONTEND_BASE_URL.rstrip('/')}/financial-alerts/{alert['id']}",
        **(extra or {}),
    }
    html = template_renderer.render(f"{template}.html", context)
    text = template_renderer.render_text(f"{template}.txt", context)
    seen: set[str] = set()
    for address in addresses:
        key = (address or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            await service.send_email(
                to_email=address.strip(), subject=subject, html_body=html, plain_text_body=text,
                email_type=email_type, recipient_type="user",
                reference_type="financial_alerts", reference_id=str(alert["id"]),
            )
        except Exception:  # noqa: BLE001 - one bad address must not stop the others
            logger.exception("Financial alert %s: email to %s failed", alert["id"], address)


def _claim(db: Client, alert_id: str, column: str) -> bool:
    """Set the timestamp once, so two runs never send the same alert twice."""
    rows = (
        db.table("financial_alerts").update({column: _now()}).eq("id", alert_id).is_(column, "null").execute()
    ).data or []
    return bool(rows)


async def _escalate(db: Client, service: EmailService, alert: dict, why: str) -> None:
    if not await run_in_threadpool(_claim, db, str(alert["id"]), "escalated_at"):
        return
    people = await run_in_threadpool(_role_users, db, "executive")
    title = f"Executive escalation: {alert['project_name']}"
    await run_in_threadpool(
        lambda: _notify(db, people, alert, ntype="contingency_escalation", title=title,
                        message=f"{why} {alert.get('message') or ''}")
    )
    await _email(
        service, [u["email"] for u in people if u.get("email")], alert,
        template="contingency_executive_escalation", email_type="contingency_escalation",
        subject=title, extra={"why": why},
    )


async def _send_one(db: Client, service: EmailService, alert: dict) -> bool:
    if not await run_in_threadpool(_claim, db, str(alert["id"]), "notified_at"):
        return False
    ntype, template, email_type, label = _KINDS[alert["alert_type"]]
    people, emails = await run_in_threadpool(_recipients, db, alert)
    title = f"{label}: {alert['project_name']}"
    await run_in_threadpool(
        lambda: _notify(db, people, alert, ntype=ntype, title=title, message=alert.get("message") or "")
    )
    await _email(
        service, [u["email"] for u in people if u.get("email")] + emails, alert,
        template=template, email_type=email_type, subject=title,
    )
    if alert["severity"] == "critical":
        await _escalate(db, service, alert, "The project's contingency is below zero.")
    return True


def _load(db: Client, alert_ids: list[str]) -> list[dict]:
    if not alert_ids:
        return []
    return (
        db.table("v_financial_alerts").select("*").in_("id", [str(i) for i in alert_ids]).execute()
    ).data or []


async def send_new(db: Client, service: EmailService, *, alert_ids: list[str]) -> int:
    sent = 0
    for alert in await run_in_threadpool(_load, db, alert_ids):
        try:
            sent += await _send_one(db, service, alert)
        except Exception:  # noqa: BLE001
            logger.exception("Financial alert %s: sending failed", alert.get("id"))
    return sent


# ── Daily sweep ─────────────────────────────────────────────────────────────


def _open_alerts(db: Client, project_id: str) -> tuple[list[dict], int]:
    rows = (
        db.table("v_financial_alerts").select("*").eq("project_id", project_id)
        .in_("status", ["open", "acknowledged"]).in_("alert_type", list(fh.ALERT_TYPES)).execute()
    ).data or []
    return rows, int(float(get_settings(db).get("alert_escalation_days") or 0))


async def sweep_project(db: Client, service: EmailService, project_id: str, now: datetime) -> dict:
    """Send alerts that were never sent, escalate the ones left undecided."""
    counts = {"sent": 0, "escalated": 0}
    alerts, days = await run_in_threadpool(_open_alerts, db, project_id)
    for alert in alerts:
        if not alert.get("notified_at"):
            counts["sent"] += await _send_one(db, service, alert)
        opened = datetime.fromisoformat(str(alert["created_at"]).replace("Z", "+00:00"))
        if not alert.get("escalated_at") and alert["severity"] != "critical" and (now - opened).days >= days:
            await _escalate(
                db, service, alert, f"No proceed or hold decision after {(now - opened).days} day(s).",
            )
            counts["escalated"] += 1
    return counts


# ── Decisions ───────────────────────────────────────────────────────────────


async def decided(db: Client, service: EmailService, *, alert: dict, actor: dict) -> None:
    try:
        who = actor.get("full_name") or actor.get("email") or "A manager"
        hold = alert["decision"] == "hold"
        verdict = "placed on hold" if hold else "OK to proceed"
        title = f"{alert['project_name']}: {verdict}"
        people, _ = await run_in_threadpool(_recipients, db, alert)
        people = [u for u in people if str(u["id"]) != str(actor["user_id"])]
        message = f"{who} decided: {verdict}. Reason: {alert['decision_reason']}"
        await run_in_threadpool(
            lambda: _notify(db, people, alert, ntype="financial_alert_decision", title=title, message=message)
        )
        if hold:
            executives = await run_in_threadpool(_role_users, db, "executive")
            await _email(
                service, [u["email"] for u in executives if u.get("email")], alert,
                template="contingency_executive_escalation", email_type="contingency_escalation",
                subject=title, extra={"why": message},
            )
    except Exception:  # noqa: BLE001
        logger.exception("Financial alert %s: decision notifications failed", alert.get("id"))


async def hold_lifted(db: Client, *, alert: dict, actor: dict, reason: str) -> None:
    try:
        who = actor.get("full_name") or actor.get("email") or "A manager"
        people, _ = await run_in_threadpool(_recipients, db, alert)
        people = [u for u in people if str(u["id"]) != str(actor["user_id"])]
        await run_in_threadpool(
            lambda: _notify(
                db, people, alert, ntype="financial_hold_lifted",
                title=f"{alert['project_name']}: hold lifted", message=f"{who} lifted the hold. Reason: {reason}",
            )
        )
    except Exception:  # noqa: BLE001
        logger.exception("Financial alert %s: hold-lifted notifications failed", alert.get("id"))
