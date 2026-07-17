"""
Milestone check-in / PM-alert email send helpers (Phase 10.4).

Renders and dispatches the milestone transactional emails. Two public
coroutines:

  - send_milestone_check_email:    vendor-facing start/progress/completion
                                     check-in. Carries ONE magic link to the
                                     portal (never an answer-bearing link):
                                     the Yes/No buttons live in the portal
                                     behind the vendor JWT, so an email
                                     scanner that pre-fetches links cannot
                                     answer on the vendor's behalf.
  - send_milestone_pm_alert_email: internal PM alert for a delay or a
                                     no-response. Both PAUSE the check-in
                                     cycle, so the email states the stall
                                     plainly and links straight to the
                                     milestone page.

Both mirror `bid_revision_service.send_revision_request_email`: one joined
read → build context → render html + txt → build subject in Python →
`await email_service.send_email(...)`. Neither ever raises; a failed send must
not break a milestone transition or crash a scheduler job; it is logged (the
email_log row EmailService writes is the retry surface).

They differ in what they hand back. send_milestone_pm_alert_email returns True
iff the provider reported 'sent'. send_milestone_check_email returns the
EmailSendResult itself (None if it never reached the send), because ONLY vendor
check-ins need their email_log row linked back to the milestone_alerts row: that
FK is how the no-response job tells a bounce apart from vendor silence, and
`result.log_id` is the only way the caller learns the row id. PM alerts have no
such consumer, so they stay on the simpler bool.

URL contracts (built by the CALLER for the portal link, here for the
milestone link, since PORTAL_BASE_URL serves both SPAs; there is no separate
dashboard base URL):
  - portal_url (passed in; token minting is Phase 10.2):
        f"{settings.PORTAL_BASE_URL}/milestone/{raw_token}"
  - milestone_url (built here):
        f"{settings.PORTAL_BASE_URL}/projects/{project_id}/tasks/{task_id}/milestones/{milestone_id}"

DEDUP NOTE for Phase 10.3 (not built here): milestone emails must NOT dedup on
(milestone_id, day) the way the bid-reminder job dedups on (invitation, day).
A one-day milestone (start_date == end_date) legitimately sends BOTH a start
check and a completion check on the same calendar day, and a milestone-keyed
daily dedup would swallow the second. Dedup on
milestone_alerts (milestone_id, alert_type, cycle_number) instead; one check
of each type per cycle, and a reschedule (which bumps milestones.cycle_number)
correctly re-enables them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from app.core.config import settings
from app.services.bid_package_service import _format_date_only

if TYPE_CHECKING:
    from app.services.email_service import EmailSendResult

logger = logging.getLogger(__name__)


# check_type -> (template stem, subject builder taking (milestone_name, project_name))
_CHECK_TEMPLATES: dict[str, tuple[str, Any]] = {
    "start": (
        "milestone_start_check",
        lambda m, p: f"Quick check-in: {m} at {p}",
    ),
    "progress": (
        "milestone_progress_check",
        lambda m, p: f"On track? {m} at {p}",
    ),
    "completion": (
        "milestone_completion_check",
        lambda m, p: f"Is {m} complete?",
    ),
}

# alert_type -> (template stem, subject builder taking (milestone_name, project_name))
_ALERT_TEMPLATES: dict[str, tuple[str, Any]] = {
    "delay": (
        "milestone_delay_alert",
        lambda m, p: f"Delay reported: {m} at {p}",
    ),
    "no_response": (
        "milestone_no_response_alert",
        lambda m, p: f"No response: {m} at {p}",
    ),
}


def _fetch_milestone_email_context(db, milestone_id: UUID | str) -> dict | None:
    """One joined read resolving milestone → task/project and → contract/vendor.

    Returns a flat dict of the fields the templates need, or None if the
    milestone can't be read.
    """
    try:
        resp = (
            db.table("milestones")
            .select(
                "id, name, start_date, end_date, task_id, contract_id,"
                " tasks!inner(name, project_id, projects(name)),"
                " contracts!inner(vendor_id, vendors(company_name))"
            )
            .eq("id", str(milestone_id))
            .single()
            .execute()
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to fetch milestone email context for %s", milestone_id
        )
        return None

    m = resp.data or {}
    task = m.get("tasks") or {}
    project = task.get("projects") or {}
    contract = m.get("contracts") or {}
    vendor = contract.get("vendors") or {}

    return {
        "milestone_id": str(m.get("id") or milestone_id),
        "milestone_name": m.get("name") or "",
        "start_date": m.get("start_date"),
        "end_date": m.get("end_date"),
        "task_id": task.get("id") or m.get("task_id"),
        "project_id": task.get("project_id"),
        "task_name": task.get("name") or "",
        "project_name": project.get("name") or "",
        "vendor_id": contract.get("vendor_id"),
        "vendor_company_name": vendor.get("company_name") or "",
    }


def _fetch_primary_contact(db, vendor_id: UUID | str | None) -> dict:
    """The vendor's primary contact row, or {} if none / on error."""
    if not vendor_id:
        return {}
    try:
        resp = (
            db.table("vendor_contacts")
            .select("full_name, email, phone")
            .eq("vendor_id", str(vendor_id))
            .eq("is_primary", True)
            .limit(1)
            .execute()
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to fetch primary contact for vendor %s", vendor_id)
        return {}
    rows = resp.data or []
    return rows[0] if rows else {}


async def send_milestone_check_email(
    *,
    milestone_id: UUID | str,
    check_type: Literal["start", "progress", "completion"],
    portal_url: str,
    db,
    email_service: Any,
) -> "EmailSendResult | None":
    """Render and send a vendor milestone check-in email. Best-effort.

    Carries a single magic link (`portal_url`) to the portal. Never raises.

    Returns the EmailSendResult of the attempt, or None when we never got as far
    as sending (unknown check_type, unreadable context, no deliverable address,
    render failure, or the send itself raised). Check `.status == "sent"` for
    success; a truthy result alone does NOT mean delivered.

    The result is returned rather than a bool because the caller needs
    `result.log_id` to stamp milestone_alerts.email_log_id, which is what lets the
    no-response job tell a bounce apart from vendor silence. A FAILED send returns
    its result for the same reason: 'failed' is an undelivered status there, so
    linking that log row is what makes the failure read as a delivery problem.
    """
    if check_type not in _CHECK_TEMPLATES:
        logger.error("Unknown milestone check_type: %r", check_type)
        return None
    stem, build_subject = _CHECK_TEMPLATES[check_type]

    ctx = _fetch_milestone_email_context(db, milestone_id)
    if ctx is None:
        return None

    contact = _fetch_primary_contact(db, ctx["vendor_id"])
    to_email = (contact.get("email") or "").strip()
    if not to_email:
        logger.warning(
            "Milestone %s has no deliverable primary-contact email; skipping "
            "%s check-in send",
            milestone_id,
            check_type,
        )
        return None

    render_ctx = {
        "vendor_contact_name": contact.get("full_name") or "",
        "company_name": ctx["vendor_company_name"],
        "project_name": ctx["project_name"],
        "task_name": ctx["task_name"],
        "milestone_name": ctx["milestone_name"],
        "start_date_formatted": _format_date_only(ctx["start_date"]),
        "end_date_formatted": _format_date_only(ctx["end_date"]),
        "portal_url": portal_url,
    }

    from app.services.template_renderer import template_renderer

    try:
        html_body = template_renderer.render(f"{stem}.html", render_ctx)
        text_body = template_renderer.render_text(f"{stem}.txt", render_ctx)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to render milestone %s check-in email for %s",
            check_type,
            milestone_id,
        )
        return None

    subject = build_subject(ctx["milestone_name"], ctx["project_name"])
    try:
        return await email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=text_body,
            email_type="milestone_alert",
            recipient_type="vendor_contact",
            reference_type="milestones",
            reference_id=str(milestone_id),
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Milestone %s check-in email send raised for %s",
            check_type,
            milestone_id,
        )
        return None


async def send_milestone_pm_alert_email(
    *,
    milestone_id: UUID | str,
    alert_type: Literal["delay", "no_response"],
    recipient_user_id: UUID | str,
    db,
    email_service: Any,
    check_type_label: str | None = None,
    days_silent: int | None = None,
) -> bool:
    """Render and send an internal PM alert (delay / no-response). Best-effort.

    Surfaces the vendor's contact details and states plainly that automated
    check-ins stay paused until the PM acts. Returns True iff the provider
    reported 'sent'. Never raises.
    """
    if alert_type not in _ALERT_TEMPLATES:
        logger.error("Unknown milestone alert_type: %r", alert_type)
        return False
    stem, build_subject = _ALERT_TEMPLATES[alert_type]

    ctx = _fetch_milestone_email_context(db, milestone_id)
    if ctx is None:
        return False

    # Recipient (the PM): need their email to send and name for the greeting.
    try:
        user_resp = (
            db.table("users")
            .select("full_name, email")
            .eq("id", str(recipient_user_id))
            .single()
            .execute()
        )
        recipient = user_resp.data or {}
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to fetch PM recipient %s for milestone %s alert",
            recipient_user_id,
            milestone_id,
        )
        return False

    to_email = (recipient.get("email") or "").strip()
    if not to_email:
        logger.warning(
            "PM recipient %s for milestone %s has no email; skipping %s alert",
            recipient_user_id,
            milestone_id,
            alert_type,
        )
        return False

    contact = _fetch_primary_contact(db, ctx["vendor_id"])
    milestone_url = (
        f"{settings.PORTAL_BASE_URL}/projects/{ctx['project_id']}"
        f"/tasks/{ctx['task_id']}/milestones/{ctx['milestone_id']}"
    )

    render_ctx = {
        "recipient_full_name": recipient.get("full_name") or "",
        "project_name": ctx["project_name"],
        "task_name": ctx["task_name"],
        "milestone_name": ctx["milestone_name"],
        "vendor_company_name": ctx["vendor_company_name"],
        "vendor_contact_name": contact.get("full_name") or "",
        "vendor_contact_email": contact.get("email") or "",
        "vendor_contact_phone": contact.get("phone") or "",
        "end_date_formatted": _format_date_only(ctx["end_date"]),
        "milestone_url": milestone_url,
        "check_type_label": check_type_label,
        "days_silent": days_silent,
    }

    from app.services.template_renderer import template_renderer

    try:
        html_body = template_renderer.render(f"{stem}.html", render_ctx)
        text_body = template_renderer.render_text(f"{stem}.txt", render_ctx)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to render milestone %s PM alert for %s",
            alert_type,
            milestone_id,
        )
        return False

    subject = build_subject(ctx["milestone_name"], ctx["project_name"])
    try:
        result = await email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=text_body,
            email_type="milestone_alert",
            recipient_type="user",
            reference_type="milestones",
            reference_id=str(milestone_id),
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Milestone %s PM alert send raised for %s", alert_type, milestone_id
        )
        return False

    return getattr(result, "status", None) == "sent"
