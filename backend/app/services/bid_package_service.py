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

from postgrest.exceptions import APIError
from starlette.concurrency import run_in_threadpool

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


def _format_date_only(value) -> str:
    """Format a date / ISO date string as 'September 15, 2026'. None → ''."""
    if value in (None, ""):
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%B %d, %Y")
    try:
        dt = datetime.fromisoformat(str(value))
        return dt.strftime("%B %d, %Y")
    except (ValueError, TypeError):
        return str(value)


def _is_unique_violation(err: APIError) -> bool:
    """supabase-py wraps Postgres 23505 in APIError. Same logic as
    award_service._is_unique_violation."""
    code = getattr(err, "code", None)
    msg = str(err).lower()
    return code == "23505" or "duplicate key" in msg or "unique" in msg


def _is_foreign_key_violation(err: APIError) -> bool:
    """Postgres 23503 (FK violation) wrapped in APIError. Raised by the creation
    RPC when task_id / template / vendor / contact / document references don't
    exist, so we can surface a clean 404 instead of a 500."""
    code = getattr(err, "code", None)
    msg = str(err).lower()
    return code == "23503" or "foreign key" in msg or "violates foreign key" in msg


def _set_invitation_send_status(db, invitation_id: str, *, sent: bool) -> None:
    """Reconcile a 'pending_send' invitation after its email attempt.

    sent=True  -> status 'sent' with sent_at = now.
    sent=False -> status 'send_failed' (recoverable via Resend / Send Bid Link).
    No-op when invitation_id is empty (defensive; the RPC always returns one).
    """
    if not invitation_id:
        return
    if sent:
        update = {
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        update = {"status": "send_failed"}
    db.table("bid_invitations").update(update).eq(
        "id", str(invitation_id)
    ).execute()


def _is_no_rows_error(err: APIError) -> bool:
    """PostgREST raises PGRST116 from .single() when zero rows match. Treat that
    as 'not found' so callers get None instead of a 500 (same principle as the
    maybe_single handling in routers/vendors.py)."""
    code = str(getattr(err, "code", "") or "")
    msg = str(getattr(err, "message", "") or str(err)).lower()
    return "PGRST116" in code or "0 rows" in msg or "no rows" in msg


def _query_one(db, table_name: str, record_id: str | UUID) -> dict | None:
    """Fetch a single record by ID. Returns None if not found or empty.

    .single() raises an APIError (PGRST116) when no row matches; we map that to
    None so a missing task / template / vendor / contact / invitation surfaces
    as a clean 4xx rather than crashing the request with a 500. Other API errors
    propagate unchanged.
    """
    try:
        resp = (
            db.table(table_name)
            .select("*")
            .eq("id", str(record_id))
            .single()
            .execute()
        )
    except APIError as exc:
        if _is_no_rows_error(exc):
            return None
        raise
    if not resp:
        return None
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
    scope_of_work_document_id = payload.get("scope_of_work_document_id")
    project_document_ids = payload.get("project_document_ids", [])
    vendor_selections = payload.get("vendor_selections", [])
    desired_start_date = payload.get("desired_start_date")

    # ── 2. Fetch task (if available) ─────────────────────────────────────
    task = _query_one(db, "tasks", task_id)

    # ── 3. Validate task attributes when data is present ─────────────────
    if task:
        if task.get("deleted_at"):
            raise BidPackageValidationError(404, "Task not found")

        # Gate positively on 'competitive' rather than excluding 'internal', so
        # a bid type that is not a real flow (a legacy 'direct_assign' row) fails
        # closed here instead of entering the pipeline, emailing vendors, and
        # then dead-ending at the scoring gate with no path to award.
        task_bid_type = task.get("bid_type")
        if task_bid_type != "competitive":
            raise BidPackageValidationError(
                400,
                "Only competitive tasks can have bid packages "
                f"(bid_type={task_bid_type!r}).",
            )

        if task.get("status") in _TERMINAL_TASK_STATUSES:
            raise BidPackageValidationError(
                400,
                f"Task with status '{task['status']}' cannot have new bid packages",
            )

        # Block when the parent project is archived
        task_project_id = task.get("project_id")
        if task_project_id:
            parent_project = _query_one(db, "projects", task_project_id)
            if parent_project and parent_project.get("archived_at") is not None:
                raise BidPackageValidationError(
                    400,
                    "Cannot create bid packages for a task on an archived project. "
                    "Unarchive the project first.",
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

        # Validate the mandatory Scope of Work document: it must exist, belong
        # to the task's project, and be a SoW (not a general reference doc).
        sow_doc = _query_one(db, "project_documents", scope_of_work_document_id)
        if not sow_doc:
            raise BidPackageValidationError(
                422, f"Scope of Work document {scope_of_work_document_id} not found"
            )
        if sow_doc.get("project_id") != task_project_id:
            raise BidPackageValidationError(
                422,
                "Scope of Work document does not belong to the task's project",
            )
        if sow_doc.get("document_kind") != "scope_of_work":
            raise BidPackageValidationError(
                422,
                "Scope of Work document must have document_kind='scope_of_work'",
            )

    # ── All validation passed. Create everything atomically, then email. ──

    # ── 7. Generate one magic-link token per vendor ──────────────────────
    # Raw tokens are emailed and never stored; only their SHA-256 hashes go
    # into the DB (inside the RPC). Keep the raw tokens in memory keyed by
    # vendor so the email phase below can build each personalized link.
    raw_token_by_vendor: dict[str, str] = {}
    rpc_vendors: list[dict] = []
    for vs in vendor_selections:
        raw_token, token_hash = _generate_magic_link_token()
        raw_token_by_vendor[vs["vendor_id"]] = raw_token
        rpc_vendors.append({
            "vendor_id": str(vs["vendor_id"]),
            "vendor_contact_id": str(vs["vendor_contact_id"]),
            "token_hash": token_hash,
        })

    # ── 8. Atomic DB write: package + documents + invitations + tokens ───
    # fn_create_bid_package_with_invitations runs in a single transaction, so an
    # interrupted create can never leave a partial package or orphan tokens (the
    # old per-row inserts could, which led to duplicate packages on PM retry).
    # Invitations start as 'pending_send'; the email phase below reconciles each
    # to 'sent' or 'send_failed'. The draft->bidding task flip happens in the RPC.
    rpc_params = {
        "p_task_id": str(task_id),
        "p_deadline": deadline_str,
        "p_bid_template_id": str(bid_template_id),
        "p_created_by": str(created_by),
        "p_instructions": payload.get("instructions"),
        "p_desired_start_date": desired_start_date,
        "p_scope_of_work_document_id": (
            str(scope_of_work_document_id) if scope_of_work_document_id else None
        ),
        "p_project_document_ids": [str(d) for d in project_document_ids],
        "p_vendors": rpc_vendors,
    }
    try:
        rpc_resp = await run_in_threadpool(
            lambda: db.rpc(
                "fn_create_bid_package_with_invitations", rpc_params
            ).execute()
        )
    except APIError as exc:
        # The whole transaction rolls back on any error, so nothing partial
        # survives. Map the common constraint failures to clean 4xx responses.
        if _is_unique_violation(exc):
            raise BidPackageValidationError(
                409,
                "A duplicate invitation already exists for this bid package.",
            ) from exc
        if _is_foreign_key_violation(exc):
            raise BidPackageValidationError(
                404,
                "Task not found or a referenced record no longer exists.",
            ) from exc
        raise

    rpc_data = rpc_resp.data
    rpc_result = rpc_data[0] if isinstance(rpc_data, list) else rpc_data
    if not isinstance(rpc_result, dict) or not rpc_result.get("bid_package_id"):
        raise BidPackageValidationError(500, "Bid package creation failed")

    bid_package_id = rpc_result["bid_package_id"]
    round_number = rpc_result.get("round_number", 1)
    invitation_id_by_vendor = {
        row["vendor_id"]: row["invitation_id"]
        for row in (rpc_result.get("invitations") or [])
        if isinstance(row, dict)
    }

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

    # Human-format the desired start date for the email; None → "" so the
    # template's {% if desired_start_date %} branch omits the row cleanly.
    formatted_desired_start = _format_date_only(desired_start_date)

    # ── 10. Send emails and reconcile each invitation's status ───────────
    # The package, invitations (pending_send) and tokens already exist from the
    # atomic RPC above. Here we only render + send, then flip each invitation to
    # 'sent' (provider accepted) or 'send_failed' (recoverable via resend).
    invitations_sent = 0
    invitations_failed = 0
    failed_vendors: list[dict] = []

    for i, vs in enumerate(vendor_selections):
        vid = vs["vendor_id"]
        cid = vs["vendor_contact_id"]

        invitation_id = invitation_id_by_vendor.get(vid, "")
        raw_token = raw_token_by_vendor.get(vid, "")

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

        # Build magic link URL from the raw token minted before the RPC
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
            "desired_start_date": formatted_desired_start,
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
                _set_invitation_send_status(db, invitation_id, sent=True)
            else:
                invitations_failed += 1
                failed_vendors.append({
                    "vendor_id": str(vid),
                    "error": result.error or "Unknown error",
                })
                _set_invitation_send_status(db, invitation_id, sent=False)
                logger.warning(
                    "Email failed for vendor %s: %s", vid, result.error
                )
        except Exception as exc:
            invitations_failed += 1
            failed_vendors.append({
                "vendor_id": str(vid),
                "error": str(exc),
            })
            _set_invitation_send_status(db, invitation_id, sent=False)
            logger.error("Email send exception for vendor %s: %s", vid, exc)

        # Rate limiting between sends (skip after last vendor)
        if i < len(vendor_selections) - 1:
            await asyncio.sleep(_RATE_LIMIT_DELAY)

    # ── 11. Build and return response ────────────────────────────────────
    # (The draft->bidding task flip already happened inside the RPC transaction.)
    return {
        "bid_package_id": str(bid_package_id),
        "round_number": round_number,
        "invitations_sent": invitations_sent,
        "invitations_failed": invitations_failed,
        "failed_vendors": failed_vendors,
        "deadline": deadline_str,
        "instructions": payload.get("instructions"),
        "desired_start_date": desired_start_date,
    }


# ── Resend invitation ───────────────────────────────────────────────────


async def resend_bid_link(
    *,
    invitation_id: UUID,
    current_user_id: UUID,
    db,
    email_service,
    template_renderer,
) -> dict:
    """Resend a bid link: hard-revoke prior tokens, mint a new one, email it.

    Each prior token is stamped with `revoked_at = NOW()` and
    `revoked_by = current_user_id` (in addition to the legacy `is_used`
    flag) so the validate-token endpoint rejects them with 410. The new
    token row is inserted with `revoked_at` left NULL.

    Raises:
        BidPackageValidationError: 404 if the invitation, bid package, or
            vendor_contact lookup is empty; 400 if the package is not open.
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
            f"Cannot resend bid link for bid package with status "
            f"'{bid_package['status']}' (must be 'open')",
        )

    # ── 3. Fetch contact BEFORE any writes — fail loud if missing ────────
    # Doing the contact lookup before token writes means a deleted contact
    # can't leave a half-revoked / half-issued token state behind.
    contact_id = invitation.get("vendor_contact_id")
    contact = _query_one(db, "vendor_contacts", contact_id) if contact_id else None
    if not contact:
        raise BidPackageValidationError(
            404, "Vendor contact not found for this invitation"
        )
    contact_email = contact.get("email", "")
    contact_name = contact.get("full_name", "")

    # ── 4. Hard-revoke all prior tokens for this invitation ──────────────
    now_iso = datetime.now(timezone.utc).isoformat()
    db.table("magic_link_tokens").update(
        {
            "is_used": True,
            "revoked_at": now_iso,
            "revoked_by": str(current_user_id),
        }
    ).eq("bid_invitation_id", str(invitation_id)).execute()

    # ── 5. Generate new (live, non-revoked) token ────────────────────────
    raw_token, token_hash = _generate_magic_link_token()
    deadline_str = bid_package.get("deadline", "")

    token_row = {
        "bid_invitation_id": str(invitation_id),
        "vendor_id": invitation.get("vendor_id", ""),
        "token_hash": token_hash,
        "expires_at": deadline_str,
        "is_used": False,
        "revoked_at": None,
    }
    db.table("magic_link_tokens").insert(token_row).execute()

    # ── 6. Fetch remaining context for email (task, project, vendor, template, PM, docs)
    task_id = bid_package.get("task_id")
    task = _query_one(db, "tasks", task_id) if task_id else None
    task_name = task.get("name", "") if isinstance(task, dict) else ""
    task_description = task.get("description", "") if isinstance(task, dict) else ""

    project_id = task.get("project_id") if isinstance(task, dict) else None
    project = _query_one(db, "projects", project_id) if project_id else None
    project_name = project.get("name", "") if isinstance(project, dict) else ""
    project_description = project.get("description", "") if isinstance(project, dict) else ""
    project_location = ""
    if isinstance(project, dict):
        city = project.get("city", "") or ""
        state = project.get("state", "") or ""
        parts = [p for p in [city, state] if p]
        project_location = ", ".join(parts) if parts else ""

    vendor_id = invitation.get("vendor_id")
    vendor = _query_one(db, "vendors", vendor_id) if vendor_id else None
    company_name = vendor.get("company_name", "") if isinstance(vendor, dict) else ""

    bid_template_id = bid_package.get("bid_template_id")
    bid_template = _query_one(db, "bid_templates", bid_template_id) if bid_template_id else None
    is_lump_sum = bid_template.get("is_lump_sum", True) if isinstance(bid_template, dict) else True
    bid_format = "Lump Sum" if is_lump_sum else "Line-Item Breakdown"

    pm_user_id = bid_package.get("created_by")
    pm_user = _query_one(db, "users", pm_user_id) if pm_user_id else None
    pm_name = pm_user.get("full_name", "") if isinstance(pm_user, dict) else ""
    pm_email = pm_user.get("email", "") if isinstance(pm_user, dict) else ""

    bp_docs_resp = (
        db.table("bid_package_documents")
        .select("project_document_id")
        .eq("bid_package_id", str(bid_package_id))
        .execute()
    )
    document_names: list[str] = []
    for row in (bp_docs_resp.data or []):
        doc = _query_one(db, "project_documents", row["project_document_id"])
        if isinstance(doc, dict):
            document_names.append(doc.get("file_name", ""))

    # ── 7. Build context and render email ────────────────────────────────
    magic_link_url = f"{settings.PORTAL_BASE_URL}/bid/{raw_token}"

    context = {
        "vendor_contact_name": contact_name,
        "vendor_company_name": company_name,
        "project_name": project_name,
        "project_location": project_location,
        "project_description": project_description,
        "task_name": task_name,
        "task_description": task_description,
        "deadline": _format_deadline(deadline_str),
        "bid_deadline": _format_deadline(deadline_str),
        "bid_format": bid_format,
        "document_names": document_names,
        "magic_link_url": magic_link_url,
        "pm_name": pm_name,
        "pm_email": pm_email,
        "desired_start_date": _format_date_only(bid_package.get("desired_start_date")),
    }

    html_body = template_renderer.render("bid_invitation.html", context)
    plain_text_body = template_renderer.render_text("bid_invitation.txt", context)

    # ── 8. Send email ────────────────────────────────────────────────────
    # A pending_send / send_failed invitation was never actually delivered, so
    # this is a first send, not a resend; label the subject accordingly.
    current_status = invitation.get("status")
    never_delivered = current_status in ("pending_send", "send_failed")
    subject = (
        f"Bid Invitation: {task_name} - {project_name}"
        if never_delivered
        else "Bid Link (Resent)"
    )
    email_result = await email_service.send_email(
        to_email=contact_email,
        subject=subject,
        html_body=html_body,
        plain_text_body=plain_text_body,
        email_type="bid_invitation",
        recipient_type="vendor_contact",
        reference_type="bid_invitations",
        reference_id=str(invitation_id),
    )

    # ── 9. Reconcile invitation status ───────────────────────────────────
    # Never-delivered (pending_send / send_failed): record the real outcome via
    # the shared helper ('sent' on success, 'send_failed' on failure). Already
    # delivered: only refresh sent_at and leave status / opened_at intact so a
    # resend never downgrades an 'opened' invitation back to 'sent'.
    if never_delivered:
        _set_invitation_send_status(
            db, str(invitation_id), sent=email_result.status == "sent"
        )
    else:
        db.table("bid_invitations").update(
            {"sent_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", str(invitation_id)).execute()

    return {
        "invitation_id": str(invitation_id),
        "vendor_id": invitation.get("vendor_id", ""),
        "new_token_generated": True,
        "email_status": email_result.status,
    }
