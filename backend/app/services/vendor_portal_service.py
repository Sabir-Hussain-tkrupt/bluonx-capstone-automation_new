"""
Vendor portal bid context assembly + submission helpers (Phase 5).

Public surface used by Tasks 5.2–5.6:
  - build_bid_context                           — Task 5.2 / 5.3
  - assert_package_open_and_before_deadline     — Task 5.3 / 5.5 / 5.6
  - fetch_template_items_map                    — Task 5.3
  - compute_line_total / build_line_item_rows   — Task 5.3
  - load_draft_response                         — Task 5.3 / 5.6 (POST/PUT return)
  - fetch_submission_detail                     — Task 5.3 (GET submission)
  - fetch_attachments                           — Task 5.5
  - resolve_unique_filename                     — Task 5.5

Why bundle build_bid_context: the portal renders a multi-step form against
one invitation. Splitting this into several endpoints would force the
frontend to sequence fetches and handle partial-load states — not worth
the complexity when the data all lives behind one invitation id.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.models.vendor_portal import (
    AttachmentResponse,
    BidDraftLineItemModel,
    BidDraftModel,
    DraftLineItemInput,
    PortalBidPackageModel,
    PortalBidTemplateModel,
    PortalProjectDocumentModel,
    PortalProjectModel,
    PortalTaskModel,
    PortalTemplateItemModel,
    PortalVendorModel,
    RevisionPrefillLineItem,
    RevisionPrefillResponse,
    SubmissionLineItemResponse,
    SubmissionResponse,
    VendorBidContextModel,
    VendorRevisionContextModel,
)

logger = logging.getLogger(__name__)


def _parse_timestamptz(value: str | datetime) -> datetime:
    """Parse a Postgres timestamptz — may arrive with or without a tz offset."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def build_bid_context(
    db,
    bid_invitation_id: UUID,
    bid_revision_request_id: UUID | None = None,
) -> VendorBidContextModel:
    """Assemble the full VendorBidContext payload for a validated invitation.

    Assumes the invitation has already been authorized (either via magic link
    validation or vendor JWT) — this function does no permission checks.

    When `bid_revision_request_id` is set the vendor entered via a revision
    link: a `revision_context` block is attached and draft resumption is
    scoped to the revision draft (never the stale original draft).
    """
    invitation_row = _fetch_invitation_tree(db, bid_invitation_id)
    template_items = _fetch_template_items(db, invitation_row["bid_packages"]["bid_template_id"])
    project_documents = _fetch_project_documents(db, invitation_row["bid_package_id"])

    revision_context: VendorRevisionContextModel | None = None
    original_submission_id: UUID | None = None
    if bid_revision_request_id is not None:
        revision_context = _fetch_revision_context(db, bid_revision_request_id)
        original_submission_id = revision_context.original_submission_id

    existing_draft = _fetch_existing_draft(
        db,
        bid_invitation_id,
        template_items,
        bid_revision_request_id=bid_revision_request_id,
        original_submission_id=original_submission_id,
    )

    pkg = invitation_row["bid_packages"]
    # Resolve the SoW file name with a dedicated lookup (no nested embed —
    # bid_packages → project_documents is ambiguous in PostgREST because of the
    # bid_package_documents junction).
    sow_file_name = _fetch_sow_file_name(db, pkg.get("scope_of_work_document_id"))
    task = pkg["tasks"]
    project = task["projects"]
    trade = task["trades"]
    template = pkg["bid_templates"]
    vendor = invitation_row["vendors"]
    contact = invitation_row["vendor_contacts"]

    return VendorBidContextModel(
        vendor=PortalVendorModel(
            id=vendor["id"],
            company_name=vendor["company_name"],
            primary_contact_name=contact["full_name"],
            email=contact["email"],
            phone=contact.get("phone"),
        ),
        project=PortalProjectModel(
            id=project["id"],
            name=project["name"],
            location=project.get("city") or "",
            address=project.get("address") or "",
        ),
        task=PortalTaskModel(
            id=task["id"],
            name=task["name"],
            description=task.get("description") or "",
            trade_name=trade["name"] if trade else "",
        ),
        bid_package=PortalBidPackageModel(
            id=pkg["id"],
            round_number=pkg["round_number"],
            deadline=pkg["deadline"],
            instructions=pkg.get("instructions") or "",
            desired_start_date=pkg.get("desired_start_date"),
            scope_of_work_document_id=pkg.get("scope_of_work_document_id"),
            scope_of_work_file_name=sow_file_name,
        ),
        bid_template=PortalBidTemplateModel(
            id=template["id"],
            name=template["name"],
            is_lump_sum=template["is_lump_sum"],
            items=template_items,
        ),
        project_documents=project_documents,
        existing_draft=existing_draft,
        revision_context=revision_context,
    )


# ── Internal fetchers ────────────────────────────────────────────────────


def _fetch_invitation_tree(db, bid_invitation_id: UUID) -> dict:
    """Single joined fetch: invitation → vendor + contact + package → task → project + trade + template."""
    resp = (
        db.table("bid_invitations")
        .select(
            "id, vendor_id, vendor_contact_id, bid_package_id,"
            " vendors(id, company_name),"
            " vendor_contacts(id, full_name, email, phone),"
            " bid_packages("
            "   id, round_number, deadline, instructions, bid_template_id, task_id,"
            "   desired_start_date, scope_of_work_document_id,"
            "   tasks("
            "     id, name, description,"
            "     projects(id, name, city, address),"
            "     trades(id, name)"
            "   ),"
            "   bid_templates(id, name, is_lump_sum)"
            " )"
        )
        .eq("id", str(bid_invitation_id))
        .single()
        .execute()
    )
    if not resp.data:
        # This should be unreachable: the caller has already validated the
        # invitation exists. Raise a plain error — the router wraps it.
        raise RuntimeError(f"Bid invitation not found: {bid_invitation_id}")
    return resp.data


def _fetch_sow_file_name(db, scope_of_work_document_id: str | None) -> str | None:
    """File name of the package's Scope of Work document, or None if unset."""
    if not scope_of_work_document_id:
        return None
    resp = (
        db.table("project_documents")
        .select("file_name")
        .eq("id", str(scope_of_work_document_id))
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0].get("file_name") if rows else None


def _fetch_template_items(db, bid_template_id: str | None) -> list[PortalTemplateItemModel]:
    if not bid_template_id:
        return []
    resp = (
        db.table("bid_template_items")
        .select("id, description, item_type, unit_of_measure, sort_order")
        .eq("bid_template_id", str(bid_template_id))
        .order("sort_order")
        .execute()
    )
    return [PortalTemplateItemModel(**row) for row in (resp.data or [])]


def _fetch_project_documents(db, bid_package_id: str) -> list[PortalProjectDocumentModel]:
    """Project documents linked to this bid package via bid_package_documents."""
    resp = (
        db.table("bid_package_documents")
        .select("project_documents(id, file_name, file_size, uploaded_at)")
        .eq("bid_package_id", str(bid_package_id))
        .execute()
    )
    out: list[PortalProjectDocumentModel] = []
    for row in resp.data or []:
        doc = row.get("project_documents")
        if not doc:
            continue
        out.append(
            PortalProjectDocumentModel(
                id=doc["id"],
                file_name=doc["file_name"],
                file_size_bytes=doc.get("file_size") or 0,
                uploaded_at=doc["uploaded_at"],
            )
        )
    return out


def _fetch_revision_context(
    db, bid_revision_request_id: UUID
) -> VendorRevisionContextModel:
    """Load the revision request + the original submission's revision_number.

    Caller (`build_bid_context`) only invokes this for revision tokens, and
    the validator has already proven the request exists and is pending — so a
    missing row here is an invariant breach, not a vendor-facing condition.
    """
    rev_resp = (
        db.table("bid_revision_requests")
        .select("id, pm_note, revision_deadline, original_submission_id")
        .eq("id", str(bid_revision_request_id))
        .single()
        .execute()
    )
    if not rev_resp.data:
        raise RuntimeError(
            f"Bid revision request not found: {bid_revision_request_id}"
        )
    rev = rev_resp.data

    orig_resp = (
        db.table("bid_submissions")
        .select("revision_number")
        .eq("id", rev["original_submission_id"])
        .single()
        .execute()
    )
    if not orig_resp.data:
        raise RuntimeError(
            f"Original submission not found: {rev['original_submission_id']}"
        )

    return VendorRevisionContextModel(
        bid_revision_request_id=rev["id"],
        pm_note=rev["pm_note"],
        revision_deadline=rev["revision_deadline"],
        original_submission_id=rev["original_submission_id"],
        original_revision_number=orig_resp.data["revision_number"],
    )


def _fetch_existing_draft(
    db,
    bid_invitation_id: UUID,
    template_items: list[PortalTemplateItemModel],
    bid_revision_request_id: UUID | None = None,
    original_submission_id: UUID | None = None,
) -> BidDraftModel | None:
    """Hydrate the in-progress draft submission, if one exists.

    For a revision link the probe is scoped to the revision draft via
    `supersedes_submission_id = original_submission_id`, so a vendor never
    resumes their stale original draft. `is_superseded = FALSE` is always
    applied — a no-op on current data, but it defends against a superseded
    history row ever transitioning back to a draft.
    """
    query = (
        db.table("bid_submissions")
        .select(
            "id, vendor_notes, total_amount, updated_at, is_draft,"
            " proposed_start_date, sow_attested_name"
        )
        .eq("bid_invitation_id", str(bid_invitation_id))
        .eq("is_draft", True)
        .eq("is_superseded", False)
    )
    if bid_revision_request_id is not None:
        query = query.eq(
            "supersedes_submission_id", str(original_submission_id)
        )
    resp = query.limit(1).execute()
    rows = resp.data or []
    if not rows:
        return None

    draft = rows[0]
    draft_id = draft["id"]

    # Map template_item_id ← template.sort_order → draft line.sort_order.
    # bid_line_items does not carry template_item_id in the current schema
    # (see handoff doc). We align by sort_order, which is the natural key
    # within a template. If Task 5.3 later adds a template_item_id column,
    # this lookup collapses to a direct read.
    sort_to_template_id: dict[int, str] = {
        item.sort_order: str(item.id) for item in template_items
    }

    line_items_resp = (
        db.table("bid_line_items")
        .select("sort_order, quantity, unit_price, lump_sum_amount")
        .eq("bid_submission_id", draft_id)
        .order("sort_order")
        .execute()
    )
    line_items: list[BidDraftLineItemModel] = []
    for row in line_items_resp.data or []:
        template_item_id = sort_to_template_id.get(row["sort_order"])
        if not template_item_id:
            # Template changed since the draft was saved. Skip the orphan
            # line rather than poison the whole hydrate.
            logger.warning(
                "Draft %s has line with sort_order=%s not in current template",
                draft_id,
                row["sort_order"],
            )
            continue
        line_items.append(
            BidDraftLineItemModel(
                template_item_id=template_item_id,
                quantity=row.get("quantity"),
                unit_price=row.get("unit_price"),
                lump_sum_amount=row.get("lump_sum_amount"),
            )
        )

    attachments_resp = (
        db.table("bid_attachments")
        .select("id")
        .eq("bid_submission_id", draft_id)
        .execute()
    )
    attachment_ids = [row["id"] for row in (attachments_resp.data or [])]

    return BidDraftModel(
        id=draft_id,
        vendor_notes=draft.get("vendor_notes") or "",
        total_amount=draft.get("total_amount"),
        line_items=line_items,
        attachment_ids=attachment_ids,
        last_saved_at=draft["updated_at"],
        proposed_start_date=draft.get("proposed_start_date"),
        sow_attested_name=draft.get("sow_attested_name"),
    )


def build_revision_prefill(
    db, original_submission_id: UUID, template_id: str | UUID | None
) -> RevisionPrefillResponse:
    """Original submission's data shaped for the revision form prefill.

    bid_line_items carries no template_item_id; we derive it via the
    sort_order ↔ template.sort_order map, exactly as _fetch_existing_draft
    does. Orphan lines (sort_order not in the current template) are
    skipped with a warning rather than poisoning the whole prefill.
    """
    sub_resp = (
        db.table("bid_submissions")
        .select("id, vendor_notes, total_amount, proposed_start_date")
        .eq("id", str(original_submission_id))
        .limit(1)
        .execute()
    )
    sub_rows = sub_resp.data or []
    if not sub_rows:
        # Unreachable: the caller already validated this submission.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    sub = sub_rows[0]

    template_map = fetch_template_items_map(db, template_id)
    sort_to_template_id: dict[int, str] = {
        row["sort_order"]: tid for tid, row in template_map.items()
    }

    li_resp = (
        db.table("bid_line_items")
        .select(
            "description, item_type, quantity, unit_of_measure,"
            " unit_price, lump_sum_amount, line_total, sort_order"
        )
        .eq("bid_submission_id", str(original_submission_id))
        .order("sort_order")
        .execute()
    )
    line_items: list[RevisionPrefillLineItem] = []
    for row in li_resp.data or []:
        template_item_id = sort_to_template_id.get(row["sort_order"])
        if not template_item_id:
            logger.warning(
                "Submission %s has line with sort_order=%s not in current "
                "template — skipping in revision prefill",
                original_submission_id,
                row["sort_order"],
            )
            continue
        line_items.append(
            RevisionPrefillLineItem(
                template_item_id=template_item_id,
                description=row["description"],
                item_type=row["item_type"],
                quantity=row.get("quantity"),
                unit_of_measure=row.get("unit_of_measure"),
                unit_price=row.get("unit_price"),
                lump_sum_amount=row.get("lump_sum_amount"),
                line_total=row["line_total"],
                sort_order=row["sort_order"],
            )
        )

    att_resp = (
        db.table("bid_attachments")
        .select("id")
        .eq("bid_submission_id", str(original_submission_id))
        .execute()
    )
    attachment_ids = [r["id"] for r in (att_resp.data or [])]

    return RevisionPrefillResponse(
        total_amount=sub.get("total_amount"),
        vendor_notes=sub.get("vendor_notes") or "",
        line_items=line_items,
        attachment_ids=attachment_ids,
        proposed_start_date=sub.get("proposed_start_date"),
    )


# ── Submission write helpers (Tasks 5.3–5.6) ─────────────────────────────


def assert_package_open_and_before_deadline(db, bid_package_id: UUID) -> None:
    """Guard every draft/submit/upload/delete write.

    Raises 423 with a distinct detail string so the frontend can tell
    "closed by PM" apart from "deadline passed mid-session" and show the
    right modal copy.
    """
    resp = (
        db.table("bid_packages")
        .select("status, deadline")
        .eq("id", str(bid_package_id))
        .single()
        .execute()
    )
    if not resp.data:
        # Unreachable via vendor JWT: the package is pinned at token-issue
        # time. Treat as 404 defensively.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bid package not found",
        )
    pkg = resp.data
    if pkg["status"] != "open":
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Bidding for this package is closed",
        )
    deadline = _parse_timestamptz(pkg["deadline"])
    if deadline <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="The bid deadline has passed",
        )


def assert_revision_request_active(db, bid_revision_request_id: UUID) -> None:
    """Revision-path analogue of assert_package_open_and_before_deadline.

    Mirrors the decline guard (bid_revision_service.decline_*) but
    ADDITIONALLY enforces revision_deadline > NOW(): a revision token is
    valid against the per-request deadline + status, never the package
    deadline / package status.
    """
    resp = (
        db.table("bid_revision_requests")
        .select("id, status, revision_deadline")
        .eq("id", str(bid_revision_request_id))
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Revision request not found",
        )
    rr = rows[0]
    if rr["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This revision request is no longer active",
        )
    deadline = _parse_timestamptz(rr["revision_deadline"])
    if deadline <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This revision request is no longer active",
        )


def fetch_template_items_map(db, bid_template_id: str | UUID | None) -> dict[str, dict]:
    """Return {template_item_id: row} with description/item_type/uom/sort_order.

    Used by POST/PUT to copy template-owned fields into `bid_line_items`, so
    submissions are decoupled from future template edits (per Task 5.4).
    """
    if not bid_template_id:
        return {}
    resp = (
        db.table("bid_template_items")
        .select("id, description, item_type, unit_of_measure, sort_order")
        .eq("bid_template_id", str(bid_template_id))
        .order("sort_order")
        .execute()
    )
    return {row["id"]: row for row in (resp.data or [])}


def fetch_template_metadata(db, bid_template_id: str | UUID) -> dict:
    """Fetch the bid_templates row itself — mainly for `is_lump_sum`."""
    resp = (
        db.table("bid_templates")
        .select("id, is_lump_sum")
        .eq("id", str(bid_template_id))
        .single()
        .execute()
    )
    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bid template not found",
        )
    return resp.data


def compute_line_total(
    item_type: str,
    quantity: Decimal | None,
    unit_price: Decimal | None,
    lump_sum_amount: Decimal | None,
) -> Decimal:
    """Compute line_total for a bid_line_items row.

    Drafts may be partial (missing quantity / price), so missing inputs
    fall back to 0 and the row is still persistable. The submit-time
    validator (`validate_for_submit`) catches "required but missing" — we
    do NOT double-enforce that here.
    """
    if item_type == "lump_sum":
        return Decimal(lump_sum_amount) if lump_sum_amount is not None else Decimal("0")
    # unit_price
    q = Decimal(quantity) if quantity is not None else Decimal("0")
    u = Decimal(unit_price) if unit_price is not None else Decimal("0")
    return q * u


def build_line_item_rows(
    payload_items: list[DraftLineItemInput],
    template_map: dict[str, dict],
    bid_submission_id: str,
) -> list[dict]:
    """Zip payload line items with their template metadata → insert-ready rows.

    Raises 422 if a client sends a template_item_id that isn't in the
    current template (defense against tampered clients; triggers the
    validator-style error shape).
    """
    rows: list[dict] = []
    unknown: list[str] = []
    for idx, li in enumerate(payload_items):
        key = str(li.template_item_id)
        tpl = template_map.get(key)
        if not tpl:
            unknown.append(f"line_items[{idx}].template_item_id")
            continue
        line_total = compute_line_total(
            tpl["item_type"], li.quantity, li.unit_price, li.lump_sum_amount
        )
        rows.append(
            {
                "bid_submission_id": bid_submission_id,
                "description": tpl["description"],
                "item_type": tpl["item_type"],
                "quantity": str(li.quantity) if li.quantity is not None else None,
                "unit_of_measure": tpl.get("unit_of_measure"),
                "unit_price": str(li.unit_price) if li.unit_price is not None else None,
                "lump_sum_amount": (
                    str(li.lump_sum_amount) if li.lump_sum_amount is not None else None
                ),
                "line_total": str(line_total),
                "sort_order": tpl["sort_order"],
            }
        )
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": "Submission contains unknown template items",
                "errors": [
                    {"field": f, "message": "Template item not in current bid template"}
                    for f in unknown
                ],
            },
        )
    return rows


def load_draft_response(db, bid_submission_id: str) -> BidDraftModel:
    """Re-read a submission as a draft response (shape matches existing_draft).

    Used as the return value of POST/PUT so the frontend always gets the
    authoritative server state, not a stale echo of the request.
    """
    sub_resp = (
        db.table("bid_submissions")
        .select(
            "id, vendor_notes, total_amount, updated_at, proposed_start_date,"
            " sow_attested_name,"
            " bid_invitations!inner(bid_packages!inner(bid_template_id))"
        )
        .eq("id", bid_submission_id)
        .single()
        .execute()
    )
    if not sub_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    row = sub_resp.data
    template_id = row["bid_invitations"]["bid_packages"]["bid_template_id"]

    template_items = list(fetch_template_items_map(db, template_id).values())
    sort_to_tpl_id: dict[int, str] = {t["sort_order"]: t["id"] for t in template_items}

    li_resp = (
        db.table("bid_line_items")
        .select("sort_order, quantity, unit_price, lump_sum_amount")
        .eq("bid_submission_id", bid_submission_id)
        .order("sort_order")
        .execute()
    )
    line_items: list[BidDraftLineItemModel] = []
    for li in li_resp.data or []:
        tpl_id = sort_to_tpl_id.get(li["sort_order"])
        if not tpl_id:
            continue
        line_items.append(
            BidDraftLineItemModel(
                template_item_id=tpl_id,
                quantity=li.get("quantity"),
                unit_price=li.get("unit_price"),
                lump_sum_amount=li.get("lump_sum_amount"),
            )
        )

    att_resp = (
        db.table("bid_attachments")
        .select("id")
        .eq("bid_submission_id", bid_submission_id)
        .execute()
    )
    attachment_ids = [r["id"] for r in (att_resp.data or [])]

    return BidDraftModel(
        id=row["id"],
        vendor_notes=row.get("vendor_notes") or "",
        total_amount=row.get("total_amount"),
        line_items=line_items,
        attachment_ids=attachment_ids,
        last_saved_at=row["updated_at"],
        proposed_start_date=row.get("proposed_start_date"),
        sow_attested_name=row.get("sow_attested_name"),
    )


def fetch_submission_detail(db, bid_submission_id: str) -> SubmissionResponse:
    """Full submission detail used by GET /submissions/{id}."""
    sub_resp = (
        db.table("bid_submissions")
        .select(
            "id, status, is_draft, total_amount, vendor_notes,"
            " submitted_at, updated_at, proposed_start_date"
        )
        .eq("id", bid_submission_id)
        .single()
        .execute()
    )
    if not sub_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )
    sub = sub_resp.data

    li_resp = (
        db.table("bid_line_items")
        .select(
            "id, description, item_type, quantity, unit_of_measure,"
            " unit_price, lump_sum_amount, line_total, sort_order"
        )
        .eq("bid_submission_id", bid_submission_id)
        .order("sort_order")
        .execute()
    )
    line_items = [SubmissionLineItemResponse(**row) for row in (li_resp.data or [])]

    attachments = fetch_attachments(db, bid_submission_id)

    return SubmissionResponse(
        id=sub["id"],
        status=sub["status"],
        is_draft=sub["is_draft"],
        total_amount=sub.get("total_amount"),
        vendor_notes=sub.get("vendor_notes") or "",
        submitted_at=sub.get("submitted_at"),
        updated_at=sub["updated_at"],
        line_items=line_items,
        attachments=attachments,
        proposed_start_date=sub.get("proposed_start_date"),
    )


def fetch_attachments(db, bid_submission_id: str) -> list[AttachmentResponse]:
    resp = (
        db.table("bid_attachments")
        .select("id, file_name, file_size, file_type, uploaded_at")
        .eq("bid_submission_id", bid_submission_id)
        .order("uploaded_at")
        .execute()
    )
    out: list[AttachmentResponse] = []
    for row in resp.data or []:
        out.append(
            AttachmentResponse(
                id=row["id"],
                file_name=row["file_name"],
                file_size=row.get("file_size") or 0,
                file_type=row.get("file_type"),
                uploaded_at=row["uploaded_at"],
            )
        )
    return out


def _format_currency(amount: Decimal | float | str | None) -> str:
    """USD formatting for email receipts. Falls back to '—' for null totals."""
    if amount is None:
        return "—"
    try:
        value = Decimal(str(amount))
    except (ArithmeticError, ValueError):
        return str(amount)
    # locale-agnostic USD; the portal is US-only in MVP per PROJECT_PLAN
    return f"${value:,.2f}"


def _format_submitted_at(dt: datetime) -> str:
    """Human-readable UTC timestamp for the email receipt."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%B %d, %Y at %I:%M %p UTC")


async def send_submission_confirmation_email(
    *,
    email_service: Any,
    template_renderer: Any,
    submission_id: UUID,
    submitted_at: datetime,
    total_amount: Decimal | float | str | None,
    attachment_count: int,
    context: dict,
) -> bool:
    """Render and send the bid-submission receipt email. Best-effort.

    Returns True iff the provider reported 'sent'. The caller should
    persist the bid regardless — a failed send is an ops issue (retry
    from the email_log), not a vendor-facing failure. We swallow
    exceptions here so a misconfigured provider can never reject a
    committed submission.
    """
    to_email = (context.get("vendor_email") or "").strip()
    if not to_email:
        logger.warning(
            "Submission %s has no vendor contact email; skipping confirmation send",
            submission_id,
        )
        return False

    render_ctx = {
        "vendor_contact_name": context.get("vendor_contact_name") or "",
        "vendor_company_name": context.get("vendor_company_name") or "",
        "project_name": context.get("project_name") or "",
        "task_name": context.get("task_name") or "",
        "total_amount_formatted": _format_currency(total_amount),
        "submitted_at_formatted": _format_submitted_at(submitted_at),
        "attachment_count": attachment_count,
        "pm_name": context.get("pm_name"),
        "pm_email": context.get("pm_email"),
    }

    try:
        html_body = template_renderer.render(
            "bid_submission_confirmation.html", render_ctx
        )
        text_body = template_renderer.render_text(
            "bid_submission_confirmation.txt", render_ctx
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to render confirmation email for submission %s", submission_id
        )
        return False

    subject = (
        f"Bid Received: {render_ctx['task_name']} — {render_ctx['project_name']}"
    )
    try:
        result = await email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=text_body,
            email_type="general",
            recipient_type="vendor_contact",
            reference_type="bid_submissions",
            reference_id=str(submission_id),
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Confirmation email send raised for submission %s", submission_id
        )
        return False

    return getattr(result, "status", None) == "sent"


async def send_revision_submitted_email(
    *,
    email_service: Any,
    template_renderer: Any,
    submission_id: UUID,
    submitted_at: datetime,
    total_amount: Decimal | float | str | None,
    attachment_count: int,
    context: dict,
) -> bool:
    """Render and send the revised-bid receipt. Best-effort.

    A near-clone of send_submission_confirmation_email — it REPLACES that
    receipt when the finalized submission is a revision. The two helpers
    never both fire for the same submission. Returns True iff the provider
    reported 'sent'; never raises.
    """
    to_email = (context.get("vendor_email") or "").strip()
    if not to_email:
        logger.warning(
            "Revision submission %s has no vendor contact email; skipping send",
            submission_id,
        )
        return False

    render_ctx = {
        "vendor_contact_name": context.get("vendor_contact_name") or "",
        "vendor_company_name": context.get("vendor_company_name") or "",
        "project_name": context.get("project_name") or "",
        "task_name": context.get("task_name") or "",
        "total_amount_formatted": _format_currency(total_amount),
        "submitted_at_formatted": _format_submitted_at(submitted_at),
        "attachment_count": attachment_count,
        "pm_name": context.get("pm_name"),
        "pm_email": context.get("pm_email"),
    }

    try:
        html_body = template_renderer.render(
            "bid_revision_submitted.html", render_ctx
        )
        text_body = template_renderer.render_text(
            "bid_revision_submitted.txt", render_ctx
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to render revision receipt for submission %s", submission_id
        )
        return False

    subject = (
        f"Bid Revision Received: {render_ctx['task_name']}"
        f" — {render_ctx['project_name']}"
    )
    try:
        result = await email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=text_body,
            email_type="general",
            recipient_type="vendor_contact",
            reference_type="bid_submissions",
            reference_id=str(submission_id),
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Revision receipt email send raised for submission %s", submission_id
        )
        return False

    return getattr(result, "status", None) == "sent"


def resolve_unique_filename(
    db, bucket: str, folder: str, desired_name: str
) -> str:
    """Return a filename that doesn't collide under {bucket}/{folder}/.

    Appends `-1`, `-2`, … before the extension until unique. If listing
    fails (transient), we fall back to the desired name and let the
    upload step surface the error.
    """
    try:
        listing = db.storage.from_(bucket).list(folder) or []
        existing = {item["name"] for item in listing if isinstance(item, dict) and "name" in item}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Storage list failed for %s/%s: %s", bucket, folder, exc)
        return desired_name

    if desired_name not in existing:
        return desired_name

    name, ext = os.path.splitext(desired_name)
    for i in range(1, 1000):
        candidate = f"{name}-{i}{ext}"
        if candidate not in existing:
            return candidate
    # Extremely unlikely. Fall back to a timestamp suffix.
    return f"{name}-{int(datetime.now(timezone.utc).timestamp())}{ext}"
