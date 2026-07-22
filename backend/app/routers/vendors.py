"""Vendor endpoints — /api/v1/vendors"""

from datetime import date, timedelta
from uuid import UUID

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from postgrest.exceptions import APIError
from pydantic import ValidationError
from supabase import Client

logger = logging.getLogger(__name__)

from app.core.auth import get_current_active_user, require_admin
from app.services.geocoding import geocode_address
from app.services.vendor_service import recompute_vendor_insurance_expiration
from app.core.file_validation import sanitize_filename, validate_upload
from app.core.query_filters import escape_like_pattern
from app.core.storage import delete_file, get_signed_url, unique_object_path, upload_file
from app.core.supabase_client import get_supabase
from app.models.bid_packages import EmailLogResponse
from app.models.common import SignedUrlResponse
from app.services.invitation_tracking_service import (
    InvitationTrackingError,
    get_vendor_email_log,
)
from app.models.vendors import (
    VendorBulkTradeCreate,
    VendorContactCreateInline,
    VendorContactResponse,
    VendorContactUpdate,
    VendorCreate,
    VendorDetailResponse,
    VendorDocumentResponse,
    VendorImportError,
    VendorImportRequest,
    VendorImportResponse,
    VendorImportRow,
    VendorListResponse,
    VendorResponse,
    VendorTradeWithNameResponse,
    VendorUpdate,
)

router = APIRouter()


# ── Helper: verify vendor exists and is not soft-deleted ─────────────────


def _get_vendor_or_404(db: Client, vendor_id: UUID) -> dict:
    """Fetch a vendor by ID, raise 404 if not found or soft-deleted.

    Uses maybe_single(), not single(): PostgREST's single() raises an
    APIError (PGRST116) on zero rows, which would surface as a 500. With
    maybe_single() a missing row returns data=None (and the response object
    itself may be None), which we translate into a clean 404.
    """
    response = (
        db.table("vendors")
        .select("*")
        .eq("id", str(vendor_id))
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not response or not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    return response.data


# ── Helper: block deletion of a vendor with live engagements ─────────────
#
# Soft-deleting a vendor preserves every referencing row (all FKs are
# ON DELETE RESTRICT), so historical involvement — declined/expired
# invitations, cancelled awards, completed contracts — survives the delete
# and never needs to block it. Only *active* (in-flight) relationships do:
# deleting a vendor mid-bid or mid-contract would orphan a live record and
# make the vendor vanish from pickers while obligations remain.
_ACTIVE_INVITATION_STATUSES = ("sent", "opened")
_ACTIVE_SUBMISSION_STATUSES = ("draft", "submitted", "under_review")
_ACTIVE_AWARD_STATUSES = ("pending_acceptance", "accepted")
_ACTIVE_CONTRACT_STATUSES = ("draft", "sent_for_signature", "executed", "active")


def _count_active(db: Client, table: str, vendor_id: UUID, statuses: tuple[str, ...]) -> int:
    """Count rows in `table` for this vendor whose status is in `statuses`."""
    resp = (
        db.table(table)
        .select("id", count="exact")
        .eq("vendor_id", str(vendor_id))
        .in_("status", list(statuses))
        .execute()
    )
    return resp.count or 0


def _assert_vendor_deletable(db: Client, vendor_id: UUID) -> None:
    """Raise 409 if the vendor has any active engagement in the bid pipeline.

    A vendor whose involvement is entirely terminal (or who has none) can be
    soft-deleted; its historical rows remain intact for audit.
    """
    blockers: list[str] = []
    checks = (
        ("bid_invitations", _ACTIVE_INVITATION_STATUSES, "bid invitation"),
        ("bid_submissions", _ACTIVE_SUBMISSION_STATUSES, "bid submission"),
        ("awards", _ACTIVE_AWARD_STATUSES, "award"),
        ("contracts", _ACTIVE_CONTRACT_STATUSES, "contract"),
    )
    for table, statuses, label in checks:
        n = _count_active(db, table, vendor_id, statuses)
        if n:
            blockers.append(f"{n} active {label}{'s' if n != 1 else ''}")

    if blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete vendor — it has "
                + ", ".join(blockers)
                + ". Set the vendor's status to 'inactive' to stop inviting it to "
                "new bids while preserving these records."
            ),
        )


# ── Vendors CRUD ─────────────────────────────────────────────────────────


@router.get("/vendors", response_model=VendorListResponse)
async def list_vendors(
    search: str | None = Query(default=None, description="Search by company name"),
    vendor_status: str | None = Query(default=None, alias="status", description="Filter by status"),
    onboarding_status: str | None = Query(default=None, description="Filter by onboarding status"),
    trade_id: UUID | None = Query(default=None, description="Filter by trade association"),
    sort_by: str = Query(default="company_name", description="Column to sort by"),
    sort_dir: str = Query(default="asc", description="Sort direction: asc or desc"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List all active vendors with search, filter, sort, and pagination."""

    # Build the (filtered) query — reused for the count and the page fetch.
    #
    # The trade filter is an embedded inner join rather than a two-step "fetch
    # matching vendor ids, then .in_(...)" lookup. That older shape silently
    # truncated at PostgREST's default 1000-row ceiling once a trade had enough
    # vendors, and pushed every id into the query string.
    def _filtered(select_expr: str):
        if trade_id:
            select_expr = f"{select_expr}, vendor_trades!inner(trade_id)"
        q = db.table("vendors").select(select_expr, count="exact").is_("deleted_at", "null")
        if search:
            q = q.ilike("company_name", f"%{escape_like_pattern(search)}%")
        if vendor_status:
            q = q.eq("status", vendor_status)
        if onboarding_status:
            q = q.eq("onboarding_status", onboarding_status)
        if trade_id:
            q = q.eq("vendor_trades.trade_id", str(trade_id))
        return q

    # Sorting
    allowed_sort_columns = {
        "company_name", "city", "state", "status",
        "onboarding_status", "created_at", "updated_at",
    }
    if sort_by not in allowed_sort_columns:
        sort_by = "company_name"
    ascending = sort_dir.lower() != "desc"

    offset = (page - 1) * page_size

    # Count first, then fetch the page only when it falls within range, so a
    # page past the last row returns an empty page instead of a 416/500.
    total = _filtered("id").limit(1).execute().count or 0

    items: list = []
    if offset < total:
        response = (
            _filtered("*")
            .order(sort_by, desc=not ascending)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        items = response.data or []

    return VendorListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# Static path — must be registered BEFORE /vendors/{vendor_id} so FastAPI
# doesn't try to coerce "insurance-expiring-count" into a UUID path param.
@router.get("/vendors/insurance-expiring-count")
async def get_insurance_expiring_count(
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
) -> dict:
    """Return the count of active vendors whose insurance expires in the
    next 30 days or has already lapsed. Drives the amber badge on the
    vendor list page.
    """
    today = date.today()
    cutoff = today + timedelta(days=30)
    resp = (
        db.table("vendors")
        .select("id", count="exact")
        .is_("deleted_at", "null")
        .not_.is_("insurance_expiration_date", "null")
        .lte("insurance_expiration_date", cutoff.isoformat())
        .execute()
    )
    return {"count": resp.count or 0}


@router.get("/vendors/{vendor_id}", response_model=VendorDetailResponse)
async def get_vendor(
    vendor_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single vendor by ID with all related data."""
    vendor = _get_vendor_or_404(db, vendor_id)

    # Fetch related data
    contacts_resp = (
        db.table("vendor_contacts")
        .select("*")
        .eq("vendor_id", str(vendor_id))
        .order("is_primary", desc=True)
        .order("full_name")
        .execute()
    )

    trades_resp = (
        db.table("vendor_trades")
        .select("*, trades(name, phase)")
        .eq("vendor_id", str(vendor_id))
        .execute()
    )

    documents_resp = (
        db.table("vendor_documents")
        .select("*")
        .eq("vendor_id", str(vendor_id))
        .order("uploaded_at", desc=True)
        .execute()
    )

    flags_resp = (
        db.table("vendor_flags")
        .select("*")
        .eq("vendor_id", str(vendor_id))
        .order("created_at", desc=True)
        .execute()
    )

    # Transform trades to include name/phase
    trades_with_names = []
    for vt in (trades_resp.data or []):
        trade_info = vt.get("trades") or {}
        trades_with_names.append({
            "id": vt["id"],
            "vendor_id": vt["vendor_id"],
            "trade_id": vt["trade_id"],
            "trade_name": trade_info.get("name"),
            "trade_phase": trade_info.get("phase"),
            "created_at": vt["created_at"],
        })

    return {
        **vendor,
        "contacts": contacts_resp.data or [],
        "trades": trades_with_names,
        "documents": documents_resp.data or [],
        "flags": flags_resp.data or [],
    }


def _company_name_exists(db: Client, company_name: str) -> bool:
    """True if an active (non-deleted) vendor already has this name.

    Case-insensitive exact match. The ilike pattern is the (stripped) name
    with no wildcards, so it matches whole values case-insensitively; any
    literal % / _ in the name would be treated as a wildcard by ilike, so we
    re-check each candidate with a precise normalized comparison in Python to
    avoid false positives. App-layer only — there is no DB unique constraint.
    """
    target = company_name.strip().casefold()
    if not target:
        return False
    resp = (
        db.table("vendors")
        .select("company_name")
        .is_("deleted_at", "null")
        .ilike("company_name", company_name.strip())
        .execute()
    )
    return any(
        (r.get("company_name") or "").strip().casefold() == target
        for r in (resp.data or [])
    )


async def _create_vendor_with_contacts(
    db: Client, vendor: VendorCreate, *, geocode: bool = True
) -> dict:
    """Create a vendor with its contacts and trade associations.

    Shared by POST /vendors and POST /vendors/import so both paths enforce
    identical rules: at least one contact, exactly one primary contact, and
    every VendorCreate field validation (lengths, EmailStr, enums, decimals).
    Raises HTTPException(422) on the contact rules or DB rejection; batch
    callers (import) translate those into per-row errors.

    geocode controls the address→lat/lng lookup. Both create and import pass
    True so vendors are usable by the distance filter immediately; the flag
    exists so callers can opt out when coordinates aren't needed.
    """
    contacts_data = vendor.contacts or []
    trade_ids = vendor.trade_ids or []

    # Validate: at least one contact is required
    if not contacts_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one contact with an email address is required.",
        )

    # Enforce a single primary contact.
    #   >1 marked primary  → ambiguous conflict, reject (let the user decide).
    #   exactly 1          → use it.
    #   0 marked primary   → auto-promote the first (unambiguous default).
    primary_count = sum(1 for c in contacts_data if c.is_primary)
    if primary_count > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only one contact can be marked as primary.",
        )
    if primary_count == 0:
        contacts_data[0].is_primary = True

    # Reject duplicate company names (case-insensitive) against active vendors.
    # This covers POST /vendors directly and, because import inserts each row
    # before the next is processed, also catches in-file duplicates within a
    # single import batch (row 2's check sees row 1).
    if _company_name_exists(db, vendor.company_name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A vendor named '{vendor.company_name.strip()}' already exists.",
        )

    # Build vendor insert data (exclude contacts and trade_ids)
    vendor_data = vendor.model_dump(exclude={"contacts", "trade_ids"})

    # Convert Decimal fields to string for JSON serialization
    for key in ("insurance_coverage_amount", "bonding_capacity", "latitude", "longitude"):
        if vendor_data.get(key) is not None:
            vendor_data[key] = str(vendor_data[key])

    # Convert date fields to string
    if vendor_data.get("insurance_expiration_date") is not None:
        vendor_data["insurance_expiration_date"] = vendor_data["insurance_expiration_date"].isoformat()

    # Auto-geocode if address fields are provided
    if geocode:
        address_fields = (vendor.address, vendor.city, vendor.state, vendor.zip_code)
        if any(f for f in address_fields):
            try:
                lat, lng = await geocode_address(
                    vendor.address, vendor.city, vendor.state, vendor.zip_code,
                )
                if lat is not None and lng is not None:
                    vendor_data["latitude"] = str(lat)
                    vendor_data["longitude"] = str(lng)
            except Exception as exc:
                logger.warning("Geocoding failed for vendor %s: %s", vendor.company_name, exc)

    try:
        response = db.table("vendors").insert(vendor_data).execute()
    except APIError as exc:
        logger.error("Supabase insert failed for vendors: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The submitted data was rejected. Please review the values and try again.",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create vendor",
        )

    new_vendor = response.data[0]
    new_vendor_id = new_vendor["id"]

    # Create contacts
    created_contacts = []
    for contact in contacts_data:
        contact_data = contact.model_dump()
        contact_data["vendor_id"] = new_vendor_id
        c_resp = db.table("vendor_contacts").insert(contact_data).execute()
        if c_resp.data:
            created_contacts.extend(c_resp.data)

    # Create trade associations if provided
    if trade_ids:
        rows = [{"vendor_id": new_vendor_id, "trade_id": str(tid)} for tid in trade_ids]
        db.table("vendor_trades").insert(rows).execute()

    # Fetch trade names for the response
    trades_with_names = []
    if trade_ids:
        trades_resp = (
            db.table("vendor_trades")
            .select("*, trades(name, phase)")
            .eq("vendor_id", new_vendor_id)
            .execute()
        )
        for vt in (trades_resp.data or []):
            trade_info = vt.get("trades") or {}
            trades_with_names.append({
                "id": vt["id"],
                "vendor_id": vt["vendor_id"],
                "trade_id": vt["trade_id"],
                "trade_name": trade_info.get("name"),
                "trade_phase": trade_info.get("phase"),
                "created_at": vt["created_at"],
            })

    return {
        **new_vendor,
        "contacts": created_contacts,
        "trades": trades_with_names,
        "documents": [],
        "flags": [],
    }


@router.post("/vendors", response_model=VendorDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    vendor: VendorCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new vendor with contacts and optional trade associations.

    At least one contact with an email address is required.
    """
    return await _create_vendor_with_contacts(db, vendor, geocode=True)


@router.patch("/vendors/{vendor_id}", response_model=VendorResponse)
async def update_vendor(
    vendor_id: UUID,
    vendor: VendorUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a vendor."""
    existing = _get_vendor_or_404(db, vendor_id)

    update_data = vendor.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    # Re-geocode if any address field changed
    _ADDRESS_FIELDS = {"address", "city", "state", "zip_code"}
    if _ADDRESS_FIELDS & set(update_data.keys()):
        try:
            merged_address = update_data.get("address", existing.get("address"))
            merged_city = update_data.get("city", existing.get("city"))
            merged_state = update_data.get("state", existing.get("state"))
            merged_zip = update_data.get("zip_code", existing.get("zip_code"))
            logger.info("Re-geocoding vendor %s: address=%s, city=%s, state=%s, zip=%s",
                        vendor_id, merged_address, merged_city, merged_state, merged_zip)
            lat, lng = await geocode_address(merged_address, merged_city, merged_state, merged_zip)
            logger.info("Geocode result for vendor %s: lat=%s, lng=%s", vendor_id, lat, lng)
            if lat is not None and lng is not None:
                update_data["latitude"] = lat
                update_data["longitude"] = lng
        except Exception as exc:
            logger.warning("Geocoding failed for vendor %s: %s", vendor_id, exc)

    # Convert Decimal fields to string for JSON serialization
    for key in ("insurance_coverage_amount", "bonding_capacity", "latitude", "longitude"):
        if key in update_data and update_data[key] is not None:
            update_data[key] = str(update_data[key])

    # Convert date fields to string
    if "insurance_expiration_date" in update_data and update_data["insurance_expiration_date"] is not None:
        update_data["insurance_expiration_date"] = update_data["insurance_expiration_date"].isoformat()

    try:
        response = (
            db.table("vendors")
            .update(update_data)
            .eq("id", str(vendor_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Supabase update failed for vendors/%s: %s", vendor_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The submitted data was rejected. Please review the values and try again.",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )

    return response.data[0]


@router.delete("/vendors/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor(
    vendor_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Soft-delete a vendor (sets deleted_at). Admin only.

    Project managers can deactivate a vendor (PATCH status='inactive') but
    cannot delete one. Blocked with 409 if the vendor has any active
    engagement (live bid invitation, in-flight submission, pending/accepted
    award, or active contract). Historical/terminal involvement does not
    block deletion.
    """
    _get_vendor_or_404(db, vendor_id)
    _assert_vendor_deletable(db, vendor_id)

    response = (
        db.table("vendors")
        .update({"deleted_at": "now()"})
        .eq("id", str(vendor_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )


# ── Vendor Contacts ──────────────────────────────────────────────────────


@router.get("/vendors/{vendor_id}/contacts", response_model=list[VendorContactResponse])
async def list_vendor_contacts(
    vendor_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List contacts for a vendor."""
    _get_vendor_or_404(db, vendor_id)

    response = (
        db.table("vendor_contacts")
        .select("*")
        .eq("vendor_id", str(vendor_id))
        .order("is_primary", desc=True)
        .order("full_name")
        .execute()
    )

    return response.data or []


@router.post(
    "/vendors/{vendor_id}/contacts",
    response_model=VendorContactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_vendor_contact(
    vendor_id: UUID,
    contact: VendorContactCreateInline,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Add a contact to a vendor.

    If is_primary=True, any existing primary contact is automatically demoted.
    If this is the first contact for the vendor, it is automatically set as primary.
    """
    _get_vendor_or_404(db, vendor_id)

    contact_data = contact.model_dump()
    contact_data["vendor_id"] = str(vendor_id)

    # Check existing contacts for this vendor
    existing = (
        db.table("vendor_contacts")
        .select("id, is_primary")
        .eq("vendor_id", str(vendor_id))
        .execute()
    )
    existing_contacts = existing.data or []

    # Auto-promote to primary if this is the first contact
    if len(existing_contacts) == 0:
        contact_data["is_primary"] = True

    # If marking as primary, demote all other primaries
    if contact_data.get("is_primary"):
        primary_ids = [c["id"] for c in existing_contacts if c["is_primary"]]
        for pid in primary_ids:
            db.table("vendor_contacts").update({"is_primary": False}).eq("id", pid).execute()

    response = db.table("vendor_contacts").insert(contact_data).execute()

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create contact",
        )

    return response.data[0]


@router.patch("/vendors/{vendor_id}/contacts/{contact_id}", response_model=VendorContactResponse)
async def update_vendor_contact(
    vendor_id: UUID,
    contact_id: UUID,
    contact: VendorContactUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a vendor contact.

    If is_primary is set to True, all other contacts for this vendor are
    automatically demoted to non-primary.

    Clearing is_primary on the vendor's only primary is rejected with 409: the
    invitation and milestone email paths look the recipient up by is_primary,
    so a vendor with no primary silently stops being reachable. Promoting a
    different contact is the supported way to move the flag, since that demotes
    this one as a side effect.
    """
    _get_vendor_or_404(db, vendor_id)

    update_data = contact.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    if update_data.get("is_primary") is False:
        target = (
            db.table("vendor_contacts")
            .select("is_primary")
            .eq("id", str(contact_id))
            .eq("vendor_id", str(vendor_id))
            .maybe_single()
            .execute()
        )
        # Only a contact that is currently primary can leave the vendor without
        # one; clearing the flag on any other contact is a no-op.
        if target and target.data and target.data.get("is_primary"):
            other_primaries = (
                db.table("vendor_contacts")
                .select("id", count="exact")
                .eq("vendor_id", str(vendor_id))
                .eq("is_primary", True)
                .neq("id", str(contact_id))
                .limit(1)
                .execute()
                .count
            ) or 0
            if other_primaries == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "A vendor must have a primary contact. Mark another "
                        "contact as primary instead — that will clear this one "
                        "automatically."
                    ),
                )

    # If promoting to primary, demote all other primaries first
    if update_data.get("is_primary") is True:
        existing = (
            db.table("vendor_contacts")
            .select("id, is_primary")
            .eq("vendor_id", str(vendor_id))
            .neq("id", str(contact_id))
            .eq("is_primary", True)
            .execute()
        )
        for c in (existing.data or []):
            db.table("vendor_contacts").update({"is_primary": False}).eq("id", c["id"]).execute()

    response = (
        db.table("vendor_contacts")
        .update(update_data)
        .eq("id", str(contact_id))
        .eq("vendor_id", str(vendor_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    return response.data[0]


@router.delete("/vendors/{vendor_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor_contact(
    vendor_id: UUID,
    contact_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a vendor contact.

    A vendor must keep at least one contact: creation requires one, and the
    invitation and milestone email paths resolve a recipient through the
    vendor's primary contact. Removing the last one is rejected with 409.

    If the deleted contact was primary, the first remaining contact is
    automatically promoted to primary.
    """
    _get_vendor_or_404(db, vendor_id)

    # Fetch the contact to check if it was primary
    target = (
        db.table("vendor_contacts")
        .select("id, is_primary")
        .eq("id", str(contact_id))
        .eq("vendor_id", str(vendor_id))
        .maybe_single()
        .execute()
    )
    if not target or not target.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    # Refuse to leave the vendor with no contacts at all.
    contact_count = (
        db.table("vendor_contacts")
        .select("id", count="exact")
        .eq("vendor_id", str(vendor_id))
        .limit(1)
        .execute()
        .count
    ) or 0
    if contact_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This is the vendor's only contact. Add another contact before "
                "removing this one."
            ),
        )

    was_primary = target.data.get("is_primary", False)

    # Delete the contact
    db.table("vendor_contacts").delete().eq("id", str(contact_id)).execute()

    # If we just deleted the primary, promote the first remaining contact
    if was_primary:
        remaining = (
            db.table("vendor_contacts")
            .select("id")
            .eq("vendor_id", str(vendor_id))
            .order("created_at")
            .limit(1)
            .execute()
        )
        if remaining.data:
            db.table("vendor_contacts").update({"is_primary": True}).eq("id", remaining.data[0]["id"]).execute()


# ── Vendor Trades ────────────────────────────────────────────────────────


@router.get("/vendors/{vendor_id}/trades", response_model=list[VendorTradeWithNameResponse])
async def list_vendor_trades(
    vendor_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List trade associations for a vendor."""
    _get_vendor_or_404(db, vendor_id)

    response = (
        db.table("vendor_trades")
        .select("*, trades(name, phase)")
        .eq("vendor_id", str(vendor_id))
        .execute()
    )

    trades_with_names = []
    for vt in (response.data or []):
        trade_info = vt.get("trades") or {}
        trades_with_names.append({
            "id": vt["id"],
            "vendor_id": vt["vendor_id"],
            "trade_id": vt["trade_id"],
            "trade_name": trade_info.get("name"),
            "trade_phase": trade_info.get("phase"),
            "created_at": vt["created_at"],
        })

    return trades_with_names


@router.post(
    "/vendors/{vendor_id}/trades",
    response_model=list[VendorTradeWithNameResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_vendor_trades(
    vendor_id: UUID,
    payload: VendorBulkTradeCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Bulk associate trades with a vendor. Skips duplicates."""
    _get_vendor_or_404(db, vendor_id)

    # Get existing trade associations to skip duplicates
    existing_resp = (
        db.table("vendor_trades")
        .select("trade_id")
        .eq("vendor_id", str(vendor_id))
        .execute()
    )
    existing_trade_ids = {r["trade_id"] for r in (existing_resp.data or [])}

    new_trade_ids = [
        str(tid) for tid in payload.trade_ids
        if str(tid) not in existing_trade_ids
    ]

    if new_trade_ids:
        rows = [{"vendor_id": str(vendor_id), "trade_id": tid} for tid in new_trade_ids]
        db.table("vendor_trades").insert(rows).execute()

    # Return full list with trade names
    return await list_vendor_trades(vendor_id, user, db)


@router.delete("/vendors/{vendor_id}/trades/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_vendor_trade(
    vendor_id: UUID,
    trade_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Remove a trade association from a vendor."""
    _get_vendor_or_404(db, vendor_id)

    response = (
        db.table("vendor_trades")
        .delete()
        .eq("vendor_id", str(vendor_id))
        .eq("trade_id", str(trade_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade association not found",
        )


# ── Vendor Documents ─────────────────────────────────────────────────────


@router.get("/vendors/{vendor_id}/documents", response_model=list[VendorDocumentResponse])
async def list_vendor_documents(
    vendor_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List documents for a vendor."""
    _get_vendor_or_404(db, vendor_id)

    response = (
        db.table("vendor_documents")
        .select("*")
        .eq("vendor_id", str(vendor_id))
        .order("uploaded_at", desc=True)
        .execute()
    )

    return response.data or []


VENDOR_DOC_TYPES = {"w9", "insurance_certificate", "master_trade_agreement"}
VENDOR_BUCKET = "vendor-documents"

# One current document per vendor for these types; a re-upload replaces the
# prior one, but only after the caller confirms with replace=true. Insurance
# certificates are intentionally NOT single-instance (renewals are history).
_SINGLE_INSTANCE_DOC_TYPES = {"w9", "master_trade_agreement"}
_VENDOR_DOC_LABELS = {
    "w9": "W-9",
    "insurance_certificate": "Insurance Certificate",
    "master_trade_agreement": "Master Trade Agreement",
}


@router.post(
    "/vendors/{vendor_id}/documents",
    response_model=VendorDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_vendor_document(
    vendor_id: UUID,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    expiration_date: str | None = Form(default=None),
    replace: bool = Form(default=False),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Upload a document for a vendor.

    Accepts multipart/form-data with:
    - file: the document file (PDF, JPEG, PNG; max 50MB)
    - document_type: w9 | insurance_certificate | master_trade_agreement
    - expiration_date: YYYY-MM-DD (required for insurance_certificate)
    - replace: for w9/master_trade_agreement, confirm replacing the existing one
    """
    _get_vendor_or_404(db, vendor_id)

    # Validate document_type
    if document_type not in VENDOR_DOC_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid document_type. Must be one of: {', '.join(sorted(VENDOR_DOC_TYPES))}",
        )

    # Single-instance types: block a second upload unless the caller confirms a
    # replacement. The existing rows (captured here) are removed after the new
    # one is safely stored.
    existing_single: list[dict] = []
    if document_type in _SINGLE_INSTANCE_DOC_TYPES:
        existing_single = (
            db.table("vendor_documents")
            .select("id, file_path")
            .eq("vendor_id", str(vendor_id))
            .eq("document_type", document_type)
            .execute()
        ).data or []
        if existing_single and not replace:
            label = _VENDOR_DOC_LABELS.get(document_type, document_type)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A {label} already exists for this vendor.",
            )

    # Require expiration_date for insurance_certificate
    parsed_expiration: date | None = None
    if document_type == "insurance_certificate":
        if not expiration_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="expiration_date is required for insurance_certificate.",
            )
        try:
            parsed_expiration = date.fromisoformat(expiration_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="expiration_date must be in YYYY-MM-DD format.",
            )
    elif expiration_date:
        try:
            parsed_expiration = date.fromisoformat(expiration_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="expiration_date must be in YYYY-MM-DD format.",
            )

    # Read file bytes
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty.",
        )

    # Validate file (MIME, size, magic bytes)
    content_type = file.content_type or "application/octet-stream"
    filename = sanitize_filename(file.filename or "document")
    validate_upload(file_bytes, filename, content_type, VENDOR_BUCKET)

    # Upload under a per-upload uuid segment so a same-named re-upload can't
    # collide (which used to surface as an opaque 500).
    storage_path = unique_object_path(f"{vendor_id}/{document_type}", filename)
    upload_file(db, VENDOR_BUCKET, storage_path, file_bytes, content_type)

    # Insert vendor_documents row
    doc_data: dict = {
        "vendor_id": str(vendor_id),
        "document_type": document_type,
        "file_name": filename,
        "file_path": storage_path,
        "file_size": len(file_bytes),
        "uploaded_by": user["user_id"],
        "status": "valid",
    }
    if parsed_expiration:
        doc_data["expiration_date"] = parsed_expiration.isoformat()

    response = db.table("vendor_documents").insert(doc_data).execute()

    if not response.data:
        # Clean up storage if DB insert fails
        delete_file(db, VENDOR_BUCKET, storage_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to save document record.",
        )

    new_doc = response.data[0]

    # Replacement confirmed: the new single-instance doc is stored, so remove the
    # prior row(s) and their objects. Insert-then-delete means the vendor is never
    # momentarily left with none, and it self-heals any pre-existing duplicates.
    if document_type in _SINGLE_INSTANCE_DOC_TYPES and existing_single:
        for old in existing_single:
            delete_file(db, VENDOR_BUCKET, old["file_path"])
            db.table("vendor_documents").delete().eq("id", old["id"]).execute()

    # Recompute vendors.insurance_expiration_date from the full set of valid
    # insurance certs. PostgREST has no multi-statement transaction, so the
    # vendor_documents row above is already committed when this runs — we
    # surface any failure to the caller rather than silently letting the
    # vendor field drift from the documents table.
    if document_type == "insurance_certificate":
        try:
            recompute_vendor_insurance_expiration(db, vendor_id)
        except Exception as exc:
            logger.error(
                "Insurance recompute failed for vendor %s after upload: %s",
                vendor_id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Document saved, but the vendor's insurance date may "
                    "not have updated. Please refresh and check the vendor "
                    "record."
                ),
            ) from exc

    return new_doc


@router.get(
    "/vendors/{vendor_id}/documents/{document_id}/url",
    response_model=SignedUrlResponse,
)
async def get_vendor_document_url(
    vendor_id: UUID,
    document_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Generate a signed download URL for a vendor document (1hr expiry)."""
    _get_vendor_or_404(db, vendor_id)

    doc_resp = (
        db.table("vendor_documents")
        .select("file_path")
        .eq("id", str(document_id))
        .eq("vendor_id", str(vendor_id))
        .maybe_single()
        .execute()
    )
    if not doc_resp or not doc_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    url = get_signed_url(db, VENDOR_BUCKET, doc_resp.data["file_path"])
    return SignedUrlResponse(url=url)


@router.delete("/vendors/{vendor_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor_document(
    vendor_id: UUID,
    document_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a vendor document from storage and database."""
    _get_vendor_or_404(db, vendor_id)

    # Fetch doc to get file_path and document_type before deleting
    doc_resp = (
        db.table("vendor_documents")
        .select("file_path, document_type")
        .eq("id", str(document_id))
        .eq("vendor_id", str(vendor_id))
        .maybe_single()
        .execute()
    )
    if not doc_resp or not doc_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    deleted_doc_type = doc_resp.data.get("document_type")

    # Delete from storage first
    delete_file(db, VENDOR_BUCKET, doc_resp.data["file_path"])

    # Delete DB row
    db.table("vendor_documents").delete().eq("id", str(document_id)).execute()

    # Recompute vendors.insurance_expiration_date when an insurance cert was
    # removed. Same trade-off as upload: the documents delete is already
    # committed; we surface recompute failures loudly rather than swallowing.
    if deleted_doc_type == "insurance_certificate":
        try:
            recompute_vendor_insurance_expiration(db, vendor_id)
        except Exception as exc:
            logger.error(
                "Insurance recompute failed for vendor %s after delete: %s",
                vendor_id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Document deleted, but the vendor's insurance date may "
                    "not have updated. Please refresh and check the vendor "
                    "record."
                ),
            ) from exc


# ── Email Log ────────────────────────────────────────────────────────────


@router.get(
    "/vendors/{vendor_id}/email-log",
    response_model=EmailLogResponse,
)
async def get_vendor_email_log_endpoint(
    vendor_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Return all email_log rows tied to this vendor's invitations.

    Unions email_log rows across bid_invitations, bid_revision_requests,
    and bid_submissions reference_types — see invitation_tracking_service
    for filter rationale.
    """
    _get_vendor_or_404(db, vendor_id)
    try:
        items = await get_vendor_email_log(vendor_id=vendor_id, db=db)
    except InvitationTrackingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"items": items}


# ── CSV Import ───────────────────────────────────────────────────────────


def _clean(value: str | None) -> str | None:
    """Trim a CSV cell; collapse blanks to None so required-field validation
    fires (e.g. a whitespace-only company_name becomes None → rejected)."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _import_row_to_vendor_create(row: VendorImportRow) -> VendorCreate:
    """Map a CSV row to a VendorCreate, running the full validation suite.

    A contact is built whenever any contact_* cell is present; VendorCreate /
    VendorContactCreateInline then require both a name and a valid email, so a
    half-filled contact becomes a row error rather than a silent drop. Rows
    with no contact cells produce an empty contacts list, which
    _create_vendor_with_contacts rejects (>=1 contact required).

    Raises pydantic.ValidationError for the caller to convert to a row error.
    """
    name = _clean(row.contact_name)
    email = _clean(row.contact_email)
    phone = _clean(row.contact_phone)
    title = _clean(row.contact_title)

    contacts: list[VendorContactCreateInline] = []
    if any((name, email, phone, title)):
        contacts.append(
            VendorContactCreateInline(
                full_name=name,
                email=email,
                phone=phone,
                title=title,
                is_primary=True,
            )
        )

    return VendorCreate(
        company_name=_clean(row.company_name),
        address=_clean(row.address),
        city=_clean(row.city),
        state=_clean(row.state),
        zip_code=_clean(row.zip_code),
        notes=_clean(row.notes),
        contacts=contacts,
    )


def _format_validation_error(exc: ValidationError) -> str:
    """Render a Pydantic ValidationError as a compact, human-readable message."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "__root__")
        parts.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    return "; ".join(parts) or "Invalid row"


@router.post("/vendors/import", response_model=VendorImportResponse)
async def import_vendors(
    payload: VendorImportRequest,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Bulk import vendors from parsed CSV data.

    Each row is validated and created through the same path as POST /vendors,
    so every VendorCreate rule applies (company-name length, >=1 contact,
    single primary, EmailStr, enum/decimal checks). Failures are reported
    per row in `errors`; valid rows are still imported (partial success).

    Rows with address fields are geocoded so imported vendors are immediately
    usable by the distance filter; geocoding failures are non-fatal (the
    vendor is still created without coordinates).
    """
    created = 0
    errors: list[dict] = []

    for idx, row in enumerate(payload.rows):
        try:
            vendor_create = _import_row_to_vendor_create(row)
            await _create_vendor_with_contacts(db, vendor_create, geocode=True)
            created += 1
        except ValidationError as exc:
            errors.append({"row": idx + 1, "message": _format_validation_error(exc)})
        except HTTPException as exc:
            errors.append({"row": idx + 1, "message": str(exc.detail)})
        except APIError as exc:
            errors.append({"row": idx + 1, "message": (exc.message or str(exc))[:200]})
        except Exception as exc:  # noqa: BLE001 — last-resort per-row guard
            logger.exception("Unexpected import failure on row %s", idx + 1)
            errors.append({"row": idx + 1, "message": str(exc)[:200]})

    return VendorImportResponse(created=created, errors=errors)
