"""
Decline notifications to the non-selected vendors (Task 9.6 seam).

Fired on acceptance (Connect `completed`) from the 9.3b webhook completion handler
— NOT at award creation — so we never burn the backup pool before the winner signs
(decision #5). Loops the OTHER invited vendor contacts on the winning bid package
through `EmailService.send_email` (Phase 7 semaphore + asyncio.gather concurrency),
each logged to `email_log`. The decline-email *body* polish remains 9.6; this ships
a professional baseline template so the dispatch path is functional and testable.
"""

from __future__ import annotations

import asyncio
import logging

from supabase import Client

from app.services.email_service import EmailService, create_email_provider
from app.services.pre_award_validation_service import _embed_one
from app.services.template_renderer import template_renderer

logger = logging.getLogger(__name__)

# Phase 7 convention — cap concurrent sends so a large backup pool doesn't burst
# the provider rate limit.
_MAX_CONCURRENT_SENDS = 5


def _load_other_invitations(
    *, bid_package_id: str, winning_vendor_id: str, db: Client
) -> list[dict]:
    """Invited contacts on the package, excluding the winning vendor."""
    resp = (
        db.table("bid_invitations")
        .select(
            "vendor_id, vendor_contacts!inner(full_name, email),"
            " bid_packages!inner(tasks!inner(name, projects!inner(name)))"
        )
        .eq("bid_package_id", str(bid_package_id))
        .neq("vendor_id", str(winning_vendor_id))
        .execute()
    )
    return resp.data or []


async def send_decline_notifications(
    *,
    bid_package_id: str,
    winning_vendor_id: str,
    db: Client,
    email_service: EmailService | None = None,
) -> int:
    """Send a decline email to every other invited vendor on the package.
    Returns the number of emails dispatched. Best-effort per recipient — one
    failure never blocks the rest."""
    rows = _load_other_invitations(
        bid_package_id=bid_package_id, winning_vendor_id=winning_vendor_id, db=db
    )
    if not rows:
        return 0

    service = email_service or EmailService(
        provider=create_email_provider(), db_client=db
    )
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SENDS)

    async def _send_one(row: dict) -> bool:
        contact = _embed_one(row.get("vendor_contacts"))
        to_email = contact.get("email")
        if not to_email:
            return False
        package = _embed_one(row.get("bid_packages"))
        task = _embed_one(package.get("tasks"))
        project = _embed_one(task.get("projects"))
        context = {
            "vendor_contact_name": contact.get("full_name") or "Vendor",
            "project_name": project.get("name") or "the project",
            "task_name": task.get("name") or "the contracted scope",
        }
        html_body = template_renderer.render("award_decline.html", context)
        plain_text_body = template_renderer.render_text("award_decline.txt", context)
        subject = f"Bid Update — {context['project_name']} / {context['task_name']}"
        async with semaphore:
            try:
                result = await service.send_email(
                    to_email=to_email,
                    subject=subject,
                    html_body=html_body,
                    plain_text_body=plain_text_body,
                    email_type="decline_notification",
                    recipient_type="vendor_contact",
                    reference_type="bid_packages",
                    reference_id=str(bid_package_id),
                )
                return result.status == "sent"
            except Exception:
                logger.exception("Failed to send decline email to %s", to_email)
                return False

    results = await asyncio.gather(*[_send_one(r) for r in rows])
    return sum(1 for ok in results if ok)
