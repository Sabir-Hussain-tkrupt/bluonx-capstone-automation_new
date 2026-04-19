"""
Vendor portal bid context assembly (Phase 5).

Single entry point `build_bid_context` bundles every field the portal form
needs into one call. Used by:
  - Task 5.2 — POST /vendor-auth/validate-token (this task)
  - Task 5.3 — GET  /vendor-portal/bid-context  (re-fetch for long sessions)

Why bundle: the portal renders a multi-step form against one invitation.
Splitting this into several endpoints would force the frontend to sequence
or parallelize fetches and handle partial-load states — not worth the
complexity when the data all lives behind one invitation id.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.models.vendor_portal import (
    BidDraftLineItemModel,
    BidDraftModel,
    PortalBidPackageModel,
    PortalBidTemplateModel,
    PortalProjectDocumentModel,
    PortalProjectModel,
    PortalTaskModel,
    PortalTemplateItemModel,
    PortalVendorModel,
    VendorBidContextModel,
)

logger = logging.getLogger(__name__)


def build_bid_context(db, bid_invitation_id: UUID) -> VendorBidContextModel:
    """Assemble the full VendorBidContext payload for a validated invitation.

    Assumes the invitation has already been authorized (either via magic link
    validation or vendor JWT) — this function does no permission checks.
    """
    invitation_row = _fetch_invitation_tree(db, bid_invitation_id)
    template_items = _fetch_template_items(db, invitation_row["bid_packages"]["bid_template_id"])
    project_documents = _fetch_project_documents(db, invitation_row["bid_package_id"])
    existing_draft = _fetch_existing_draft(db, bid_invitation_id, template_items)

    pkg = invitation_row["bid_packages"]
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
        ),
        bid_template=PortalBidTemplateModel(
            id=template["id"],
            name=template["name"],
            is_lump_sum=template["is_lump_sum"],
            items=template_items,
        ),
        project_documents=project_documents,
        existing_draft=existing_draft,
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


def _fetch_existing_draft(
    db,
    bid_invitation_id: UUID,
    template_items: list[PortalTemplateItemModel],
) -> BidDraftModel | None:
    """Hydrate the in-progress draft submission, if one exists."""
    resp = (
        db.table("bid_submissions")
        .select("id, vendor_notes, total_amount, updated_at, is_draft")
        .eq("bid_invitation_id", str(bid_invitation_id))
        .eq("is_draft", True)
        .limit(1)
        .execute()
    )
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
    )
