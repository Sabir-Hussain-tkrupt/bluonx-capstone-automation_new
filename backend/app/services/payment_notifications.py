"""Payment emails, in-app notifications and the finance hand-off (Phase 6 · Tasks 6.3 to 6.6).

  sent to a manager / executive → that person (else every manager / executive)
  rejected                      → the field manager; the trade is NOT told
  final approval                → trade (vendor contact): approved
                                  land team + the field manager's boss, field
                                  manager copied
                                  finance: hand-off email with the PO PDF
                                  (finance role + finance_emails)

Every email goes through EmailService (email_log). Called after commit; never
raises. A failed finance email leaves the hand-off "failed"; the daily summary
job retries it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from starlette.concurrency import run_in_threadpool
from supabase import Client

from app.core.config import settings
from app.core.storage import upload_file
from app.services import finance_exports, po_pdf
from app.services.contingency_notifications import _role_users
from app.services.contingency_service import get_settings
from app.services.email_service import Attachment, EmailService, create_email_provider
from app.services.notification_service import create_notification
from app.services.template_renderer import template_renderer
from app.services.variance_notifications import _users

logger = logging.getLogger(__name__)

FINANCE_BUCKET = "finance-documents"


def email_service(db: Client) -> EmailService:
    return EmailService(provider=create_email_provider(), db_client=db)


def _link(path: str) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{path}"


def _emails(value: Any) -> list[str]:
    return [str(v).strip() for v in value or [] if isinstance(v, str) and "@" in v]


def _rows(pa: dict) -> list[tuple[str, str]]:
    rows = [
        ("Project", pa.get("project_name")), ("Line", pa.get("line_name")), ("Trade", pa.get("trade_name")),
        ("Vendor", pa.get("vendor_name")), ("Payment", po_pdf.kind_label(pa)),
        ("Work value", po_pdf.usd(pa.get("gross_amount"))),
    ]
    if float(pa.get("retainage_amount") or 0):
        rows.append(("Retainage held", po_pdf.usd(pa.get("retainage_amount"))))
    rows.append(("Amount to pay", po_pdf.usd(pa.get("amount"))))
    if pa.get("comments"):
        rows.append(("Reason / note", pa["comments"]))
    return [(k, str(v)) for k, v in rows if v]


async def _send(
    service: EmailService, to: list[str], *, template: str, subject: str, context: dict, email_type: str,
    recipient_type: str = "user", reference: tuple[str, str] | None = None, attachments: list | None = None,
) -> str | None:
    """Send one email per address. Returns the email_log id of the first success."""
    html = template_renderer.render(f"{template}.html", context)
    text = template_renderer.render_text(f"{template}.txt", context)
    first_log: str | None = None
    seen: set[str] = set()
    for address in to:
        key = (address or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            result = await service.send_email(
                to_email=address.strip(), subject=subject, html_body=html, plain_text_body=text,
                attachments=attachments, email_type=email_type, recipient_type=recipient_type,
                reference_type=reference[0] if reference else None, reference_id=reference[1] if reference else None,
            )
            if result.status == "sent" and not first_log:
                first_log = result.log_id or "sent"
        except Exception:  # noqa: BLE001 - one bad address must not stop the others
            logger.exception("Payment email %s to %s failed", email_type, address)
    return first_log


def _notify(db: Client, users: list[dict], pa: dict, *, ntype: str, title: str, message: str) -> None:
    for u in users:
        try:
            create_notification(db, user_id=u["id"], notification_type=ntype, title=title[:255], message=message,
                                reference_type="payment_approvals", reference_id=pa["id"])
        except Exception:  # noqa: BLE001
            logger.exception("Payment %s: notification for %s failed", pa.get("id"), u.get("id"))


def _who(user: dict) -> str:
    return user.get("full_name") or user.get("email") or "Someone"


# ── After each step ─────────────────────────────────────────────────────────


async def after_step(db: Client, service: EmailService, *, pa: dict, actor: dict) -> None:
    try:
        status = pa["status"]
        ref = ("payment_approvals", str(pa["id"]))
        ctx = {"rows": _rows(pa), "link": _link(f"/payments/{pa['id']}"), "link_label": "Open the approval"}
        if status in ("awaiting_manager", "awaiting_executive"):
            if status == "awaiting_manager":
                routed = pa.get("routed_to_user_id")
                people = await run_in_threadpool(_users, db, [routed]) if routed else []
                people = people or await run_in_threadpool(_role_users, db, "project_manager")
                why = ("confirmed by an external field manager" if pa.get("confirmed_by_external")
                       else "above the first approver's limit")
                heading, ntype = "Second approval needed", "payment_approval_requested"
            else:
                people = await run_in_threadpool(_role_users, db, "executive")
                why = "above the executive approval threshold"
                heading, ntype = "Executive approval needed", "payment_approval_requested"
            people = [u for u in people if str(u["id"]) != str(actor["user_id"])]
            title = f"{heading}: {pa['project_name']} · {po_pdf.usd(pa['amount'])}"
            message = f"{_who(actor)} approved a payment on \"{pa['line_name']}\" that is {why}."
            await run_in_threadpool(lambda: _notify(db, people, pa, ntype=ntype, title=title, message=message))
            await _send(service, [u["email"] for u in people if u.get("email")], template="payment_approval_request",
                        subject=title, context={**ctx, "heading": heading, "intro": message},
                        email_type="payment_approval_request", reference=ref)
        elif status == "rejected":
            people = await run_in_threadpool(
                _users, db, [pa.get("work_confirmed_by"), pa.get("field_approved_by"), pa.get("requested_by")])
            people = [u for u in people if str(u["id"]) != str(actor["user_id"])]
            title = f"Payment rejected: {pa['project_name']} · {pa['line_name']}"
            message = (f"{_who(actor)} rejected the payment. Reason: {pa.get('rejection_reason')}. "
                       "Fix it and resubmit. The trade has not been told.")
            await run_in_threadpool(
                lambda: _notify(db, people, pa, ntype="payment_rejected", title=title, message=message))
            await _send(service, [u["email"] for u in people if u.get("email")], template="payment_rejected",
                        subject=title, context={**ctx, "heading": "Payment rejected", "intro": message},
                        email_type="payment_rejected", reference=ref)
        elif status == "approved":
            await approved(db, service, pa=pa)
    except Exception:  # noqa: BLE001
        logger.exception("Payment %s: notifications failed", pa.get("id"))


async def approved(db: Client, service: EmailService, *, pa: dict) -> None:
    ref = ("payment_approvals", str(pa["id"]))
    cfg = await run_in_threadpool(get_settings, db)
    handoff = await run_in_threadpool(_handoff_for, db, str(pa["id"]))
    payload = (handoff or {}).get("payload") or {}
    ctx = {
        "rows": _rows(pa) + [("PO number", pa.get("po_number") or payload.get("po_number") or ""),
                             ("Expected payment date", str(pa.get("expected_payment_date") or ""))],
        "approvers": po_pdf.approvers_text(payload),
    }
    title = f"Payment approved: {pa['project_name']} · {pa['line_name']} · {po_pdf.usd(pa['amount'])}"

    # Trade (vendor contact)
    if pa.get("vendor_id"):
        contacts = await run_in_threadpool(_vendor_contacts, db, str(pa["vendor_id"]))
        await _send(service, contacts, template="payment_approved_trade", subject=f"Payment approved: {pa['project_name']}",
                    context={**ctx, "heading": "Payment approved", "vendor": pa.get("vendor_name")},
                    email_type="payment_approved", recipient_type="vendor_contact", reference=ref)

    # Land team + the field manager's boss, field manager copied
    field = pa.get("work_confirmed_by") or pa.get("field_approved_by")
    people = await run_in_threadpool(_users, db, [field])
    boss_ids = []
    if people:
        row = await run_in_threadpool(
            lambda: db.table("users").select("reports_to").eq("id", str(field)).maybe_single().execute())
        boss_ids = [((row.data if row else None) or {}).get("reports_to")]
    bosses = await run_in_threadpool(_users, db, boss_ids)
    team_ctx = {**ctx, "heading": "Payment approved", "link": _link(f"/payments/{pa['id']}"),
                "link_label": "Open the approval",
                "cc": ", ".join(u.get("full_name") or u["email"] for u in people)}
    await _send(service, _emails(cfg.get("land_team_emails")) + [u["email"] for u in bosses if u.get("email")],
                template="payment_approved_team", subject=title, context=team_ctx,
                email_type="payment_approved", reference=ref)
    # No CC in the email service: the field manager gets the same email, marked as a copy.
    await _send(service, [u["email"] for u in people if u.get("email")], template="payment_approved_team",
                subject=f"Copy: {title}", context={**team_ctx, "is_copy": True},
                email_type="payment_approved", reference=ref)
    requesters = await run_in_threadpool(_users, db, [field, pa.get("requested_by")])
    await run_in_threadpool(lambda: _notify(db, requesters, pa, ntype="payment_approved", title=title,
                                            message=f"PO {payload.get('po_number')} sent to finance."))
    if handoff:
        await deliver_handoff(db, service, handoff_id=str(handoff["id"]))


# ── Finance hand-off ────────────────────────────────────────────────────────


def _handoff_for(db: Client, payment_id: str) -> dict | None:
    rows = db.table("finance_handoffs").select("*").eq("payment_approval_id", payment_id).limit(1).execute().data or []
    return rows[0] if rows else None


def _vendor_contacts(db: Client, vendor_id: str) -> list[str]:
    rows = (db.table("vendor_contacts").select("email, is_primary").eq("vendor_id", vendor_id).execute()).data or []
    primary = [r["email"] for r in rows if r.get("is_primary") and r.get("email")]
    return primary or [r["email"] for r in rows[:1] if r.get("email")]


def finance_recipients(db: Client) -> list[str]:
    people = _role_users(db, "finance")
    return [u["email"] for u in people if u.get("email")] + _emails(get_settings(db).get("finance_emails"))


def _ensure_document(db: Client, handoff: dict) -> tuple[str, bytes]:
    pdf = po_pdf.build(handoff.get("payload") or {})
    path = handoff.get("document_path") or f"{handoff['project_id']}/po/{handoff['po_number']}.pdf"
    if not handoff.get("document_path"):
        upload_file(db, FINANCE_BUCKET, path, pdf, "application/pdf")
    return path, pdf


async def deliver_handoff(db: Client, service: EmailService, *, handoff_id: str) -> bool:
    """PDF in the finance-documents bucket + the hand-off email. Never raises."""
    try:
        resp = await run_in_threadpool(
            lambda: db.table("finance_handoffs").select("*").eq("id", handoff_id).maybe_single().execute())
        handoff = resp.data if resp else None
        if not handoff:
            return False
        path, pdf = await run_in_threadpool(_ensure_document, db, handoff)
        payload = handoff.get("payload") or {}
        to = await run_in_threadpool(finance_recipients, db)
        log_id = None
        error = "No finance recipients: give someone the Finance role or add finance emails in the settings."
        if to:
            log_id = await _send(
                service, to, template="finance_handoff",
                subject=f"PO {handoff['po_number']} approved: {payload.get('vendor') or ''} {po_pdf.usd(handoff['amount'])}",
                context={"payload": payload, "approvers": po_pdf.approvers_text(payload),
                         "kind": po_pdf.kind_label(payload), "usd": po_pdf.usd,
                         "link": _link("/payments?tab=finance")},
                email_type="finance_handoff", reference=("finance_handoffs", handoff_id),
                attachments=[Attachment(f"{handoff['po_number']}.pdf", pdf, "application/pdf")],
            )
            error = None if log_id else "The finance email could not be sent."
        await run_in_threadpool(lambda: db.rpc("fn_mark_finance_handoff", {
            "p_handoff_id": handoff_id, "p_sent": bool(log_id),
            "p_email_log_id": log_id if log_id and log_id != "sent" else None,
            "p_document": path, "p_error": error,
        }).execute())
        return bool(log_id)
    except Exception:  # noqa: BLE001 - the daily job retries
        logger.exception("Finance hand-off %s failed", handoff_id)
        return False


async def daily_summary(db: Client, service: EmailService, now: datetime | None = None) -> dict:
    """Retry failed hand-offs, then email finance the last 24 hours and every
    hand-off not yet exported, with the export attached."""
    now = now or datetime.now(timezone.utc)
    counts = {"retried": 0, "delivered": 0, "in_summary": 0, "summary_sent": False}
    stale = (now - timedelta(minutes=10)).isoformat()
    retry = await run_in_threadpool(lambda: (
        db.table("finance_handoffs").select("id").in_("status", ["pending", "failed"]).lt("created_at", stale).execute()
    ).data or [])
    for h in retry:
        counts["retried"] += 1
        counts["delivered"] += await deliver_handoff(db, service, handoff_id=str(h["id"]))

    since = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = await run_in_threadpool(lambda: (
        db.table("v_finance_handoffs").select("*").or_(f"exported_at.is.null,created_at.gte.{since}")
        .order("created_at").execute()
    ).data or [])
    counts["in_summary"] = len(rows)
    to = await run_in_threadpool(finance_recipients, db)
    if not rows or not to:
        return counts
    cutoff = now - timedelta(days=1)
    new = [r for r in rows if datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")) >= cutoff]
    pending = [r for r in rows if not r.get("exported_at")]
    log = await _send(
        service, to, template="finance_daily_summary",
        subject=f"Daily finance summary: {len(new)} new approval(s), {len(pending)} not yet exported",
        context={"new": new, "pending": pending, "usd": po_pdf.usd, "approvers": po_pdf.approvers_text,
                 "link": _link("/payments?tab=finance")},
        email_type="finance_daily_summary",
        attachments=[Attachment(f"finance-handoffs-{now.date().isoformat()}.csv", finance_exports.to_csv(pending), "text/csv")],
    )
    counts["summary_sent"] = bool(log)
    return counts
