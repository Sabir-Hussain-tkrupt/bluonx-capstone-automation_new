"""
Vendor service (Task 7.4.5).

Helpers that maintain derived state on the `vendors` table from its
related rows. Currently the only operation is recomputing
`vendors.insurance_expiration_date` from `vendor_documents` so the
vendor field is a trustworthy mirror of the latest valid insurance
certificate — required by Task 7.5 (insurance expiration monitoring).
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from supabase import Client

logger = logging.getLogger(__name__)


def recompute_vendor_insurance_expiration(
    db: Client, vendor_id: UUID
) -> date | None:
    """Recompute and persist `vendors.insurance_expiration_date`.

    The vendor field mirrors MAX(expiration_date) across rows in
    `vendor_documents` where document_type='insurance_certificate' and
    status='valid'. NULL when no such rows exist.

    Returns the value written (or None).

    Raises any Supabase/PostgREST exception — the caller decides how to
    surface failures. No HTTPException is raised here.
    """
    # Supabase-py exposes no MAX aggregate; use order desc + limit 1.
    query_resp = (
        db.table("vendor_documents")
        .select("expiration_date")
        .eq("vendor_id", str(vendor_id))
        .eq("document_type", "insurance_certificate")
        .eq("status", "valid")
        .not_.is_("expiration_date", "null")
        .order("expiration_date", desc=True)
        .limit(1)
        .execute()
    )

    rows = query_resp.data or []
    new_value: date | None = None
    if rows:
        raw = rows[0].get("expiration_date")
        if raw:
            new_value = date.fromisoformat(str(raw))

    # Persist (None → NULL via supabase-py).
    db.table("vendors").update(
        {"insurance_expiration_date": new_value.isoformat() if new_value else None}
    ).eq("id", str(vendor_id)).execute()

    return new_value
