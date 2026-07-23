"""
Vendor service (Task 7.4.5).

Helpers that maintain or interrogate derived state on the `vendors` table:

- recomputing `vendors.insurance_expiration_date` from `vendor_documents` so
  the vendor field is a trustworthy mirror of the latest valid insurance
  certificate (required by Task 7.5, insurance expiration monitoring)
- deciding whether a vendor may be marked onboarding_status='complete'

Nothing here raises HTTPException; callers decide how to surface failures.
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from supabase import Client

from app.services.geocoding import normalize_address

logger = logging.getLogger(__name__)


def missing_requirements_for_complete(vendor: dict) -> list[str]:
    """What blocks this vendor from onboarding_status='complete'.

    Returns human-readable phrases for the caller to join into a message;
    empty means the vendor qualifies.

    'complete' is load-bearing, which is why it is gated at all: it is a hard
    eligibility gate in vendor_filtering (anything else is disqualified from
    bidding) and half of the compliance dimension in bid_scoring. A vendor
    marked complete with no address would score 100 there while being invisible
    to the distance filter, since a vendor with no coordinates skips the radius
    check entirely.

    Two requirements, deliberately not four:

    - ANY address field, not a street line specifically. Geocoding joins
      whatever is non-empty, so "Austin, TX" is locatable while a bare street
      line often is not. normalize_address is reused so this rule and the
      geocoder cannot drift apart on what counts as an address.
    - A valid, unexpired insurance certificate. insurance_expiration_date is
      already MAX(expiration_date) over valid insurance_certificate rows, so
      NULL means no certificate exists and a past date means the one on file
      has lapsed. One field answers both questions, and it is the same value
      pre-award validation and scoring read.

    W-9 and Master Trade Agreement are tracked but deliberately not required.
    """
    missing: list[str] = []

    if not normalize_address(
        vendor.get("address"),
        vendor.get("city"),
        vendor.get("state"),
        vendor.get("zip_code"),
    ):
        missing.append("an address (street, city, state or ZIP)")

    raw_expiry = vendor.get("insurance_expiration_date")
    if not raw_expiry:
        missing.append("a valid insurance certificate")
    else:
        expiry = raw_expiry if isinstance(raw_expiry, date) else date.fromisoformat(str(raw_expiry))
        if expiry < date.today():
            missing.append(
                f"an unexpired insurance certificate (the one on file expired {expiry.isoformat()})"
            )

    return missing


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
