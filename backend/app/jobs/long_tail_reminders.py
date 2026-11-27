"""Daily long-tail reminders (Phase 7 · Tasks 7.3 and 7.4).

  property tax  → each instalment at the city / county's lead time (default
                  30 days) and again at 7 days: project manager + finance
  bond renewal  → each open escrow's bond at bond_renewal_reminder_days
                  (default 60) and again at 14 days: project manager, field
                  manager + finance

In-app + email through EmailService (email_log). Each reminder is sent once per
tier; failures are logged and the next run retries. See README.md for the job
contract.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from apscheduler.triggers.cron import CronTrigger
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.supabase_client import get_supabase_client
from app.jobs.scheduler import DEFAULT_JOB_KWARGS, tracked_job
from app.services.contingency_notifications import _role_users
from app.services.contingency_service import get_settings
from app.services.email_service import EmailService, create_email_provider
from app.services.notification_service import create_notification
from app.services.po_pdf import usd
from app.services.template_renderer import template_renderer
from app.services.variance_notifications import _users

logger = logging.getLogger(__name__)

JOB_ID = "long_tail_reminders"
TAX_SECOND_TIER = 7
BOND_SECOND_TIER = 14
OPEN_ESCROW = ["planned", "posted", "works_built", "inspection", "corrections", "signed_off"]


def tax_tier(days_left: int, lead: int, reminded: int | None) -> int | None:
    """Which reminder is due now: lead, then 7 days. None = nothing to send."""
    if days_left < 0:
        return None
    if days_left <= TAX_SECOND_TIER and (reminded is None or reminded > TAX_SECOND_TIER):
        return TAX_SECOND_TIER
    if days_left <= lead and reminded is None:
        return lead
    return None


def bond_tier(days_left: int, lead: int, sent_tiers: set[int]) -> int | None:
    if days_left <= BOND_SECOND_TIER and BOND_SECOND_TIER not in sent_tiers:
        return BOND_SECOND_TIER
    if days_left <= lead and lead not in sent_tiers and BOND_SECOND_TIER not in sent_tiers:
        return lead
    return None


def _finance(db, cfg) -> tuple[list[dict], list[str]]:
    emails = [e for e in cfg.get("finance_emails") or [] if isinstance(e, str) and "@" in e]
    return _role_users(db, "finance"), emails


def _project_people(db, project_id: str, *, field: bool) -> list[dict]:
    resp = db.table("projects").select("name, manager_id, field_manager_id").eq("id", project_id).maybe_single().execute()
    p = (resp.data if resp else None) or {}
    people = _users(db, [p.get("manager_id")]) or _role_users(db, "project_manager")
    if field:
        people += _users(db, [p.get("field_manager_id")])
    return people


async def _send(db, service: EmailService, people: list[dict], extra: list[str], *, ntype: str, email_type: str,
                title: str, message: str, rows: list[tuple[str, str]], project_id: str) -> None:
    link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/projects/{project_id}?tab=long-tail"
    for u in {str(u["id"]): u for u in people}.values():
        try:
            await run_in_threadpool(lambda u=u: create_notification(
                db, user_id=u["id"], notification_type=ntype, title=title[:255], message=message,
                reference_type="long_tail", reference_id=project_id, dedupe=False))
        except Exception:  # noqa: BLE001
            logger.exception("Long-tail reminder: notification for %s failed", u.get("id"))
    ctx = {"heading": title, "intro": message, "rows": rows, "link": link, "link_label": "Open the long-tail view"}
    template = "property_tax_reminder" if email_type == "property_tax_reminder" else "bond_renewal_reminder"
    html = template_renderer.render(f"{template}.html", ctx)
    text = template_renderer.render_text(f"{template}.txt", ctx)
    seen: set[str] = set()
    for address in [u.get("email") for u in people] + extra:
        key = (address or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            await service.send_email(to_email=address.strip(), subject=title, html_body=html, plain_text_body=text,
                                     email_type=email_type, recipient_type="user",
                                     reference_type="projects", reference_id=project_id)
        except Exception:  # noqa: BLE001
            logger.exception("Long-tail reminder email to %s failed", address)


async def run_long_tail_reminders(db, service: EmailService, today: date | None = None) -> dict:
    today = today or date.today()
    counts = {"tax_reminders": 0, "bond_reminders": 0, "failed": 0}
    cfg = await run_in_threadpool(get_settings, db)
    finance_users, finance_emails = await run_in_threadpool(_finance, db, cfg)
    limit = asyncio.Semaphore(10)

    taxes = await run_in_threadpool(lambda: (
        db.table("v_property_taxes").select("*").in_("status", ["estimated", "billed"])
        .not_.is_("due_date", "null").execute()
    ).data or [])
    leads = {str(j["id"]): int(j.get("reminder_days_before") or 30) for j in await run_in_threadpool(lambda: (
        db.table("jurisdictions").select("id, reminder_days_before").execute()).data or [])}

    async def tax(t: dict) -> None:
        async with limit:
            try:
                days = (date.fromisoformat(str(t["due_date"])[:10]) - today).days
                tier = tax_tier(days, leads.get(str(t.get("jurisdiction_id")), 30), t.get("reminded_days"))
                if tier is None:
                    return
                people = await run_in_threadpool(_project_people, db, str(t["project_id"]), field=False)
                title = f"Property tax due in {days} day(s): {t['project_name']}"
                await _send(db, service, people + finance_users, finance_emails, ntype="property_tax_due",
                            email_type="property_tax_reminder", title=title,
                            message=f"{t['jurisdiction']} property tax {t['tax_year']}, instalment {t['installment_number']}, "
                                    f"is due on {t['due_date']}.",
                            rows=[("Project", t["project_name"]), ("City / county", t["jurisdiction"]),
                                  ("Tax year", str(t["tax_year"])), ("Instalment", str(t["installment_number"])),
                                  ("Due date", str(t["due_date"])), ("Amount due", usd(t["amount_due"])),
                                  ("Status", "Billed" if t["status"] == "billed" else "Estimated")],
                            project_id=str(t["project_id"]))
                await run_in_threadpool(lambda: db.table("property_taxes").update({"reminded_days": tier})
                                        .eq("id", t["id"]).execute())
                counts["tax_reminders"] += 1
            except Exception:  # noqa: BLE001
                counts["failed"] += 1
                logger.exception("Property tax reminder %s failed", t.get("id"))

    bond_lead = int(cfg.get("bond_renewal_reminder_days") or 60)
    escrows = await run_in_threadpool(lambda: (
        db.table("v_escrows").select("*").eq("security_form", "bond").in_("status", OPEN_ESCROW)
        .not_.is_("bond_expiry_date", "null").execute()
    ).data or [])

    async def bond(e: dict) -> None:
        async with limit:
            try:
                expiry = str(e["bond_expiry_date"])[:10]
                days = (date.fromisoformat(expiry) - today).days
                events = await run_in_threadpool(lambda: (
                    db.table("escrow_events").select("note").eq("escrow_id", e["id"])
                    .eq("event_type", "bond_reminder").execute()).data or [])
                sent = {int(n.split(":")[1]) for n in (x.get("note") or "" for x in events)
                        if n.startswith(f"{expiry}:") and n.split(":")[1].isdigit()}
                tier = bond_tier(days, bond_lead, sent)
                if tier is None:
                    return
                people = await run_in_threadpool(_project_people, db, str(e["project_id"]), field=True)
                when = "has expired" if days < 0 else f"expires in {days} day(s)"
                title = f"Bond renewal: {e['name']} {when} ({e['project_name']})"
                await _send(db, service, people + finance_users, finance_emails, ntype="bond_renewal_due",
                            email_type="bond_renewal_reminder", title=title,
                            message=f"The bond for escrow \"{e['name']}\" {when} ({expiry}). The escrow is still open, "
                                    "so renew it and record the renewal and its premium.",
                            rows=[("Project", e["project_name"]), ("Escrow", e["name"]),
                                  ("Areas", ", ".join(e.get("covered_areas") or [])),
                                  ("Holder", e.get("holder_name") or "—"), ("Bond number", e.get("bond_number") or "—"),
                                  ("Expires", expiry), ("Secured amount", usd(e["secured_amount"]))],
                            project_id=str(e["project_id"]))
                await run_in_threadpool(lambda: db.table("escrow_events").insert({
                    "escrow_id": e["id"], "project_id": e["project_id"], "event_type": "bond_reminder",
                    "status_after": e["status"], "note": f"{expiry}:{tier}"}).execute())
                await run_in_threadpool(lambda: db.table("escrows").update({"bond_reminder_sent_for": expiry})
                                        .eq("id", e["id"]).execute())
                counts["bond_reminders"] += 1
            except Exception:  # noqa: BLE001
                counts["failed"] += 1
                logger.exception("Bond reminder %s failed", e.get("id"))

    await asyncio.gather(*(tax(t) for t in taxes), *(bond(e) for e in escrows))
    return counts


@tracked_job(JOB_ID)
async def _run() -> dict:
    db = get_supabase_client()
    return await run_long_tail_reminders(db, EmailService(provider=create_email_provider(), db_client=db))


def register(scheduler) -> None:
    """Daily at 15:30 UTC (8:30 AM Mountain Standard Time)."""
    scheduler.add_job(
        _run,
        CronTrigger(hour=15, minute=30),  # 15:30 UTC = 08:30 America/Denver (MST)
        id=JOB_ID,
        replace_existing=True,
        **DEFAULT_JOB_KWARGS,
    )
    logger.info("Registered job %s (daily at 15:30 UTC)", JOB_ID)
