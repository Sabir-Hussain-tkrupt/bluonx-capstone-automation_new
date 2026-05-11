"""
PM single bid detail service (Task 6.2).

Returns a fully-hydrated bid submission for the project manager: vendor +
contact metadata, line items (sorted by sort_order), and attachments with
short-lived signed URLs. Read-only — no mutations.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.core.storage import get_signed_url

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────────

BID_ATTACHMENTS_BUCKET = "bid-attachments"
SIGNED_URL_EXPIRY_SECONDS = 3600


# ── Exceptions ─────────────────────────────────────────────────────────────


class BidSubmissionDetailError(Exception):
    """Base exception for bid submission detail operations."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class BidSubmissionNotFoundError(BidSubmissionDetailError):
    def __init__(self, detail: str = "Bid submission not found") -> None:
        super().__init__(404, detail)


# ── Helpers ────────────────────────────────────────────────────────────────


def _unwrap_one(data) -> dict | None:
    if data is None:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _unwrap_list(data) -> list[dict]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _extract_contact(invitation_join) -> dict:
    if not invitation_join:
        return {}
    if isinstance(invitation_join, list):
        invitation_join = invitation_join[0] if invitation_join else {}
    if not isinstance(invitation_join, dict):
        return {}
    contacts = invitation_join.get("vendor_contacts") or {}
    if isinstance(contacts, list):
        contacts = contacts[0] if contacts else {}
    return contacts if isinstance(contacts, dict) else {}


def _extract_vendor(vendor_join) -> dict:
    if not vendor_join:
        return {}
    if isinstance(vendor_join, list):
        vendor_join = vendor_join[0] if vendor_join else {}
    return vendor_join if isinstance(vendor_join, dict) else {}


# ── Service ────────────────────────────────────────────────────────────────


async def get_pm_bid_submission_detail(*, submission_id: UUID, db) -> dict:
    """Return the full PM-facing detail for a single bid submission.

    Raises BidSubmissionNotFoundError (404) if the submission does not exist.
    """
    sub_resp = (
        db.table("bid_submissions")
        .select(
            "id, bid_invitation_id, status, is_direct_assign, total_amount,"
            " vendor_notes, submitted_at,"
            " bid_invitations!inner(vendor_contacts(full_name, email)),"
            " vendors(company_name)"
        )
        .eq("id", str(submission_id))
        .maybe_single()
        .execute()
    )
    sub = _unwrap_one(sub_resp.data)
    if sub is None:
        raise BidSubmissionNotFoundError()

    contact = _extract_contact(sub.get("bid_invitations"))
    vendor = _extract_vendor(sub.get("vendors"))

    li_resp = (
        db.table("bid_line_items")
        .select(
            "id, description, item_type, quantity, unit_of_measure,"
            " unit_price, lump_sum_amount, line_total, sort_order"
        )
        .eq("bid_submission_id", str(submission_id))
        .order("sort_order")
        .execute()
    )
    line_items_raw = _unwrap_list(li_resp.data)
    line_items = sorted(line_items_raw, key=lambda r: r.get("sort_order") or 0)

    att_resp = (
        db.table("bid_attachments")
        .select("id, file_name, file_path, file_size, file_type, uploaded_at")
        .eq("bid_submission_id", str(submission_id))
        .execute()
    )
    attachments_raw = _unwrap_list(att_resp.data)

    attachments: list[dict] = []
    for row in attachments_raw:
        download_url = get_signed_url(
            db,
            BID_ATTACHMENTS_BUCKET,
            row.get("file_path") or "",
            expires_in=SIGNED_URL_EXPIRY_SECONDS,
        )
        attachments.append(
            {
                "id": row.get("id"),
                "file_name": row.get("file_name"),
                "file_size": row.get("file_size") or 0,
                "file_type": row.get("file_type"),
                "uploaded_at": row.get("uploaded_at"),
                "download_url": download_url,
                "download_url_expires_in": SIGNED_URL_EXPIRY_SECONDS,
            }
        )

    return {
        "id": sub.get("id"),
        "bid_invitation_id": sub.get("bid_invitation_id"),
        "status": sub.get("status"),
        "is_direct_assign": bool(sub.get("is_direct_assign")),
        "total_amount": sub.get("total_amount"),
        "vendor_notes": sub.get("vendor_notes"),
        "submitted_at": sub.get("submitted_at"),
        "vendor_company_name": vendor.get("company_name"),
        "vendor_contact_name": contact.get("full_name"),
        "vendor_contact_email": contact.get("email"),
        "line_items": line_items,
        "attachments": attachments,
    }
