"""
Bid package creation & invitation sending service (Task 4.4).

Orchestrates the full flow: validation → bid_packages row → documents →
invitations + magic link tokens → personalized emails → task status update.

This is the most complex single operation in the system, touching 5 tables
in one request with cryptographic token generation and personalized email
rendering per vendor.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID

logger = logging.getLogger(__name__)

# Statuses that block new bid packages
_TERMINAL_TASK_STATUSES = {"completed", "cancelled", "awarded"}

_RATE_LIMIT_DELAY = 0.1  # seconds between email sends


class BidPackageValidationError(Exception):
    """Raised when bid package input validation fails."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ── Helpers ──────────────────────────────────────────────────────────────


def _generate_magic_link_token() -> tuple[str, str]:
    """Generate a raw URL-safe token and its SHA-256 hash.

    Returns:
        (raw_token, token_hash) — raw token for the URL, hash for the DB.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


def _format_deadline(deadline_str: str) -> str:
    """Format an ISO deadline string into a human-readable form."""
    try:
        dt = datetime.fromisoformat(deadline_str)
        return dt.strftime("%B %d, %Y at %I:%M %p UTC")
    except (ValueError, TypeError):
        return deadline_str


def _query_one(db, table_name: str, record_id: str | UUID) -> dict | None:
    """Fetch a single record by ID. Returns None if not found or empty."""
    resp = (
        db.table(table_name)
        .select("*")
        .eq("id", str(record_id))
        .single()
        .execute()
    )
    data = resp.data
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


# ── Main orchestration ───────────────────────────────────────────────────


async def create_bid_package_with_invitations(
    *,
    task_id: UUID,
    payload: dict,
    created_by: UUID,
    db,
    email_service,
    template_renderer,
) -> dict:
    """Create a bid package with invitations, tokens, and emails.

    Args:
        task_id: The task to create a bid package for.
        payload: Dict with deadline, bid_template_id, project_document_ids,
                 vendor_selections.
        created_by: UUID of the PM creating the package (from JWT).
        db: Supabase client.
        email_service: EmailService instance for sending emails.
        template_renderer: TemplateRenderer for rendering email templates.

    Returns:
        Dict with bid_package_id, round_number, invitations_sent,
        invitations_failed, failed_vendors, deadline.

    Raises:
        BidPackageValidationError: On any validation failure.
    """
    from app.core.config import settings

    # ── 1. Parse payload ─────────────────────────────────────────────────
    deadline_str = payload["deadline"]
    bid_template_id = payload["bid_template_id"]
    project_document_ids = payload.get("project_document_ids", [])
    vendor_selections = payload.get("vendor_selections", [])

    # ── 2. Fetch task (if available) ─────────────────────────────────────
    task = _query_one(db, "tasks", task_id)

    # ── 3. Validate task attributes when data is present ─────────────────
    if task:
        if task.get("deleted_at"):
            raise BidPackageValidationError(404, "Task not found")

        if task.get("bid_type") == "internal":
            raise BidPackageValidationError(
                400, "Internal tasks cannot have bid packages"
            )

        if task.get("status") in _TERMINAL_TASK_STATUSES:
            raise BidPackageValidationError(
                400,
                f"Task with status '{task['status']}' cannot have new bid packages",
            )

    # ── 4. Validate deadline (always — payload-level check) ──────────────
    try:
        deadline_dt = datetime.fromisoformat(deadline_str)
    except (ValueError, TypeError) as exc:
        raise BidPackageValidationError(
            400, f"Invalid deadline format: {exc}"
        ) from exc

    if deadline_dt.tzinfo is None:
        deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)

    if deadline_dt <= datetime.now(timezone.utc):
        raise BidPackageValidationError(400, "Deadline must be in the future")

    # ── 5. Validate vendor_selections (always — payload-level check) ─────
    if not vendor_selections:
        raise BidPackageValidationError(
            400, "At least one vendor selection is required"
        )

    vendor_ids = [vs["vendor_id"] for vs in vendor_selections]
    if len(vendor_ids) != len(set(vendor_ids)):
        raise BidPackageValidationError(
            400, "Duplicate vendor_id in vendor_selections"
        )

    # ── 6. DB-level validation (only when task data is available) ────────
    bid_template = None
    vendor_data_map: dict[str, dict] = {}
    contact_data_map: dict[str, dict] = {}

    if task:
        # Validate bid template
        bid_template = _query_one(db, "bid_templates", bid_template_id)
        if not bid_template:
            raise BidPackageValidationError(404, "Bid template not found")

        # Validate project documents
        task_project_id = task.get("project_id")
        for doc_id in project_document_ids:
            doc = _query_one(db, "project_documents", doc_id)
            if not doc:
                raise BidPackageValidationError(
                    400, f"Project document {doc_id} not found"
                )
            if doc.get("project_id") != task_project_id:
                raise BidPackageValidationError(
                    400,
                    f"Project document {doc_id} does not belong to the task's project",
                )

        # Validate vendors and contacts
        for vs in vendor_selections:
            vid = vs["vendor_id"]
            cid = vs["vendor_contact_id"]

            vendor = _query_one(db, "vendors", vid)
            if not vendor:
                raise BidPackageValidationError(400, f"Vendor {vid} not found")
            if vendor.get("deleted_at"):
                raise BidPackageValidationError(
                    400, f"Vendor {vid} has been deleted"
                )
            if vendor.get("status") != "active":
                raise BidPackageValidationError(
                    400,
                    f"Vendor {vid} is not active (status: {vendor.get('status')})",
                )
            vendor_data_map[vid] = vendor

            contact = _query_one(db, "vendor_contacts", cid)
            if not contact:
                raise BidPackageValidationError(
                    400, f"Vendor contact {cid} not found"
                )
            if contact.get("vendor_id") != vid:
                raise BidPackageValidationError(
                    400,
                    f"Vendor contact {cid} does not belong to vendor {vid}",
                )
            contact_data_map[cid] = contact

    # ── All validation passed — start creating DB rows ───────────────────

    # ── 7. Create bid_packages row ───────────────────────────────────────
    bp_row = {
        "task_id": str(task_id),
        "deadline": deadline_str,
        "bid_template_id": str(bid_template_id),
        "created_by": str(created_by),
        "status": "open",
    }
    bp_resp = db.table("bid_packages").insert(bp_row).execute()
    bp_data = bp_resp.data
    if isinstance(bp_data, list):
        bp_record = bp_data[0] if bp_data else None
    else:
        bp_record = bp_data

    if not bp_record or (isinstance(bp_record, dict) and not bp_record.get("id")):
        raise BidPackageValidationError(
            404, "Task not found or bid package creation failed"
        )

    bid_package_id = bp_record.get("id", "") if isinstance(bp_record, dict) else str(bp_record)
    round_number = bp_record.get("round_number", 1) if isinstance(bp_record, dict) else 1

    # ── 8. Create bid_package_documents ──────────────────────────────────
    for doc_id in project_document_ids:
        db.table("bid_package_documents").insert({
            "bid_package_id": str(bid_package_id),
            "project_document_id": str(doc_id),
        }).execute()

    # ── 9. Gather shared context for emails ──────────────────────────────
    # Fetch project, PM, template info if not already cached from validation
    task_project_id = task.get("project_id", "") if task else ""

    project = _query_one(db, "projects", task_project_id) if task_project_id else None
    project_name = project.get("name", "") if isinstance(project, dict) else ""
    project_location = ""
    if isinstance(project, dict):
        city = project.get("city", "") or ""
        state = project.get("state", "") or ""
        parts = [p for p in [city, state] if p]
        project_location = ", ".join(parts) if parts else ""
    project_description = project.get("description", "") if isinstance(project, dict) else ""

    pm_user = _query_one(db, "users", created_by)
    pm_name = pm_user.get("full_name", "") if isinstance(pm_user, dict) else ""
    pm_email = pm_user.get("email", "") if isinstance(pm_user, dict) else ""

    # Bid format from template (may have been fetched during validation)
    if not bid_template:
        bid_template = _query_one(db, "bid_templates", bid_template_id)
    is_lump_sum = bid_template.get("is_lump_sum", True) if isinstance(bid_template, dict) else True
    bid_format = "Lump Sum" if is_lump_sum else "Line-Item Breakdown"

    # Document names
    document_names: list[str] = []
    for doc_id in project_document_ids:
        doc = _query_one(db, "project_documents", doc_id)
        if isinstance(doc, dict):
            document_names.append(doc.get("file_name", ""))

    formatted_deadline = _format_deadline(deadline_str)
    task_name = task.get("name", "") if isinstance(task, dict) else ""
    task_description = task.get("description", "") if isinstance(task, dict) else ""

    # ── 10. Create invitations + tokens + send emails ────────────────────
    invitations_sent = 0
    invitations_failed = 0
    failed_vendors: list[dict] = []

    for i, vs in enumerate(vendor_selections):
        vid = vs["vendor_id"]
        cid = vs["vendor_contact_id"]

        # Get vendor/contact data (from validation cache or fresh query)
        contact = contact_data_map.get(cid)
        if not contact:
            contact = _query_one(db, "vendor_contacts", cid)
        vendor = vendor_data_map.get(vid)
        if not vendor:
            vendor = _query_one(db, "vendors", vid)

        contact_email = contact.get("email", "") if isinstance(contact, dict) else ""
        contact_name = contact.get("full_name", "") if isinstance(contact, dict) else ""
        company_name = vendor.get("company_name", "") if isinstance(vendor, dict) else ""

        # Insert bid_invitations row
        inv_row = {
            "bid_package_id": str(bid_package_id),
            "vendor_id": str(vid),
            "vendor_contact_id": str(cid),
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        inv_resp = db.table("bid_invitations").insert(inv_row).execute()
        inv_data = inv_resp.data
        if isinstance(inv_data, list):
            inv_record = inv_data[0] if inv_data else {}
        else:
            inv_record = inv_data if inv_data else {}
        invitation_id = inv_record.get("id", "") if isinstance(inv_record, dict) else ""

        # Generate magic link token
        raw_token, token_hash = _generate_magic_link_token()

        # Insert magic_link_tokens row
        token_row = {
            "bid_invitation_id": str(invitation_id),
            "vendor_id": str(vid),
            "token_hash": token_hash,
            "expires_at": deadline_str,
            "is_used": False,
        }
        db.table("magic_link_tokens").insert(token_row).execute()

        # Build magic link URL
        magic_link_url = f"{settings.PORTAL_BASE_URL}/bid/{raw_token}"

        # Build email template context
        context = {
            "vendor_contact_name": contact_name,
            "vendor_company_name": company_name,
            "project_name": project_name,
            "project_location": project_location,
            "project_description": project_description,
            "task_name": task_name,
            "task_description": task_description,
            "deadline": formatted_deadline,
            "bid_deadline": formatted_deadline,
            "bid_format": bid_format,
            "document_names": document_names,
            "magic_link_url": magic_link_url,
            "pm_name": pm_name,
            "pm_email": pm_email,
        }

        # Render email templates
        html_body = template_renderer.render("bid_invitation.html", context)
        plain_text_body = template_renderer.render_text("bid_invitation.txt", context)

        # Send email
        subject = f"Bid Invitation: {task_name} — {project_name}"
        try:
            result = await email_service.send_email(
                to_email=contact_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=plain_text_body,
                email_type="bid_invitation",
                recipient_type="vendor_contact",
                reference_type="bid_invitations",
                reference_id=str(invitation_id),
            )

            if result.status == "sent":
                invitations_sent += 1
            else:
                invitations_failed += 1
                failed_vendors.append({
                    "vendor_id": str(vid),
                    "error": result.error or "Unknown error",
                })
                logger.warning(
                    "Email failed for vendor %s: %s", vid, result.error
                )
        except Exception as exc:
            invitations_failed += 1
            failed_vendors.append({
                "vendor_id": str(vid),
                "error": str(exc),
            })
            logger.error("Email send exception for vendor %s: %s", vid, exc)

        # Rate limiting between sends (skip after last vendor)
        if i < len(vendor_selections) - 1:
            await asyncio.sleep(_RATE_LIMIT_DELAY)

    # ── 11. Update task status ───────────────────────────────────────────
    if isinstance(task, dict) and task.get("status") == "draft":
        db.table("tasks").update({"status": "bidding"}).eq(
            "id", str(task_id)
        ).execute()

    # ── 12. Build and return response ────────────────────────────────────
    return {
        "bid_package_id": str(bid_package_id),
        "round_number": round_number,
        "invitations_sent": invitations_sent,
        "invitations_failed": invitations_failed,
        "failed_vendors": failed_vendors,
        "deadline": deadline_str,
    }


# ── Resend invitation ───────────────────────────────────────────────────


async def resend_invitation(
    *,
    invitation_id: UUID,
    db,
    email_service,
    template_renderer,
) -> dict:
    """Resend an invitation email with a new magic link token.

    Invalidates all previous tokens, generates a new one, renders and
    sends the email, and updates sent_at.

    Returns:
        Dict with invitation_id, vendor_id, new_token_generated, email_status.

    Raises:
        BidPackageValidationError: On validation failure.
    """
    from app.core.config import settings

    # ── 1. Fetch invitation ──────────────────────────────────────────────
    invitation = _query_one(db, "bid_invitations", invitation_id)
    if not invitation:
        raise BidPackageValidationError(404, "Invitation not found")

    # ── 2. Fetch bid package and validate status ─────────────────────────
    bid_package_id = invitation.get("bid_package_id")
    bid_package = _query_one(db, "bid_packages", bid_package_id)
    if not bid_package:
        raise BidPackageValidationError(404, "Bid package not found")

    if bid_package.get("status") != "open":
        raise BidPackageValidationError(
            400,
            f"Cannot resend invitation for bid package with status "
            f"'{bid_package['status']}' (must be 'open')",
        )

    # ── 3. Invalidate old tokens ─────────────────────────────────────────
    db.table("magic_link_tokens").update({"is_used": True}).eq(
        "bid_invitation_id", str(invitation_id)
    ).execute()

    # ── 4. Generate new token ────────────────────────────────────────────
    raw_token, token_hash = _generate_magic_link_token()
    deadline_str = bid_package.get("deadline", "")

    token_row = {
        "bid_invitation_id": str(invitation_id),
        "vendor_id": invitation.get("vendor_id", ""),
        "token_hash": token_hash,
        "expires_at": deadline_str,
        "is_used": False,
    }
    db.table("magic_link_tokens").insert(token_row).execute()

    # ── 5. Fetch contact for email ───────────────────────────────────────
    contact_id = invitation.get("vendor_contact_id")
    contact = _query_one(db, "vendor_contacts", contact_id) if contact_id else None
    contact_email = contact.get("email", "") if isinstance(contact, dict) else ""
    contact_name = contact.get("full_name", "") if isinstance(contact, dict) else ""

    # ── 6. Build context and render email ────────────────────────────────
    magic_link_url = f"{settings.PORTAL_BASE_URL}/bid/{raw_token}"

    context = {
        "vendor_contact_name": contact_name,
        "magic_link_url": magic_link_url,
        "deadline": _format_deadline(deadline_str),
        "bid_deadline": _format_deadline(deadline_str),
    }

    html_body = template_renderer.render("bid_invitation.html", context)
    plain_text_body = template_renderer.render_text("bid_invitation.txt", context)

    # ── 7. Send email ────────────────────────────────────────────────────
    email_result = await email_service.send_email(
        to_email=contact_email,
        subject="Bid Invitation (Resent)",
        html_body=html_body,
        plain_text_body=plain_text_body,
        email_type="bid_invitation",
        recipient_type="vendor_contact",
        reference_type="bid_invitations",
        reference_id=str(invitation_id),
    )

    # ── 8. Update invitation sent_at ─────────────────────────────────────
    db.table("bid_invitations").update({
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", str(invitation_id)).execute()

    # ── 9. Return result ─────────────────────────────────────────────────
    return {
        "invitation_id": str(invitation_id),
        "vendor_id": invitation.get("vendor_id", ""),
        "new_token_generated": True,
        "email_status": email_result.status,
    }
