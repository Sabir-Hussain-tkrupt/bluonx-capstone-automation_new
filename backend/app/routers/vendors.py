"""Vendor endpoints — /api/v1/vendors"""

from datetime import date, timedelta
from uuid import UUID

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from postgrest.exceptions import APIError
from supabase import Client

logger = logging.getLogger(__name__)

from app.core.auth import get_current_active_user
from app.services.geocoding import geocode_address
from app.services.vendor_service import recompute_vendor_insurance_expiration
from app.core.file_validation import sanitize_filename, validate_upload
from app.core.storage import delete_file, get_signed_url, upload_file
from app.core.supabase_client import get_supabase
from app.models.common import SignedUrlResponse
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
    VendorListResponse,
    VendorResponse,
    VendorTradeWithNameResponse,
    VendorUpdate,
)

router = APIRouter()


# ── Helper: verify vendor exists and is not soft-deleted ─────────────────


def _get_vendor_or_404(db: Client, vendor_id: UUID) -> dict:
    """Fetch a vendor by ID, raise 404 if not found or soft-deleted."""
    response = (
        db.table("vendors")
        .select("*")
        .eq("id", str(vendor_id))
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    return response.data


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

    # If filtering by trade, first get the vendor IDs that have that trade
    vendor_ids_for_trade: list[str] | None = None
    if trade_id:
        trade_resp = (
            db.table("vendor_trades")
            .select("vendor_id")
            .eq("trade_id", str(trade_id))
            .execute()
        )
        vendor_ids_for_trade = [r["vendor_id"] for r in (trade_resp.data or [])]
        if not vendor_ids_for_trade:
            return VendorListResponse(items=[], total=0, page=page, page_size=page_size)

    # Build the main query
    query = db.table("vendors").select("*", count="exact").is_("deleted_at", "null")

    if search:
        query = query.ilike("company_name", f"%{search}%")

    if vendor_status:
        query = query.eq("status", vendor_status)

    if onboarding_status:
        query = query.eq("onboarding_status", onboarding_status)

    if vendor_ids_for_trade is not None:
        query = query.in_("id", vendor_ids_for_trade)

    # Sorting
    allowed_sort_columns = {
        "company_name", "city", "state", "status",
        "onboarding_status", "created_at", "updated_at",
    }
    if sort_by not in allowed_sort_columns:
        sort_by = "company_name"

    ascending = sort_dir.lower() != "desc"
    query = query.order(sort_by, desc=not ascending)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    response = query.execute()

    return VendorListResponse(
        items=response.data or [],
        total=response.count or 0,
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


@router.post("/vendors", response_model=VendorDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    vendor: VendorCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new vendor with contacts and optional trade associations.

    At least one contact with an email address is required.
    """
    contacts_data = vendor.contacts or []
    trade_ids = vendor.trade_ids or []

    # Validate: at least one contact is required
    if not contacts_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one contact with an email address is required.",
        )

    # Ensure exactly one primary contact (first contact if none marked)
    has_primary = any(c.is_primary for c in contacts_data)
    if not has_primary:
        contacts_data[0].is_primary = True

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
            detail=f"Database rejected the data: {exc.message}",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create vendor",
        )

    new_vendor = response.data[0]
    new_vendor_id = new_vendor["id"]

    # Create contacts if provided
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
            detail=f"Database rejected the data: {exc.message}",
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
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Soft-delete a vendor (sets deleted_at)."""
    _get_vendor_or_404(db, vendor_id)

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
    """
    _get_vendor_or_404(db, vendor_id)

    update_data = contact.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
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
        .single()
        .execute()
    )
    if not target.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
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
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Upload a document for a vendor.

    Accepts multipart/form-data with:
    - file: the document file (PDF, JPEG, PNG; max 50MB)
    - document_type: w9 | insurance_certificate | master_trade_agreement
    - expiration_date: YYYY-MM-DD (required for insurance_certificate)
    """
    _get_vendor_or_404(db, vendor_id)

    # Validate document_type
    if document_type not in VENDOR_DOC_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid document_type. Must be one of: {', '.join(sorted(VENDOR_DOC_TYPES))}",
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

    # Upload to storage: {vendor_id}/{document_type}/{filename}
    storage_path = f"{vendor_id}/{document_type}/{filename}"
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

    return response.data[0]


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
        .single()
        .execute()
    )
    if not doc_resp.data:
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
        .single()
        .execute()
    )
    if not doc_resp.data:
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


# ── CSV Import ───────────────────────────────────────────────────────────


@router.post("/vendors/import", response_model=VendorImportResponse)
async def import_vendors(
    payload: VendorImportRequest,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Bulk import vendors from parsed CSV data."""
    created = 0
    errors: list[dict] = []

    for idx, row in enumerate(payload.rows):
        try:
            vendor_data = {
                "company_name": row.company_name.strip(),
                "status": "active",
                "onboarding_status": "pending",
            }

            # Add optional fields
            if row.address:
                vendor_data["address"] = row.address.strip()
            if row.city:
                vendor_data["city"] = row.city.strip()
            if row.state:
                vendor_data["state"] = row.state.strip()
            if row.zip_code:
                vendor_data["zip_code"] = row.zip_code.strip()
            if row.notes:
                vendor_data["notes"] = row.notes.strip()

            vendor_resp = db.table("vendors").insert(vendor_data).execute()

            if not vendor_resp.data:
                errors.append({"row": idx + 1, "message": "Failed to create vendor"})
                continue

            new_vendor_id = vendor_resp.data[0]["id"]

            # Create primary contact if contact info provided
            if row.contact_name and row.contact_email:
                contact_data: dict = {
                    "vendor_id": new_vendor_id,
                    "full_name": row.contact_name.strip(),
                    "email": row.contact_email.strip(),
                    "is_primary": True,
                }
                if row.contact_phone:
                    contact_data["phone"] = row.contact_phone.strip()
                if row.contact_title:
                    contact_data["title"] = row.contact_title.strip()

                db.table("vendor_contacts").insert(contact_data).execute()

            created += 1

        except Exception as e:
            error_msg = str(e)
            if "unique" in error_msg.lower() or "duplicate" in error_msg.lower():
                errors.append({"row": idx + 1, "message": f"Duplicate vendor: {row.company_name}"})
            else:
                errors.append({"row": idx + 1, "message": error_msg[:200]})

    return VendorImportResponse(created=created, errors=errors)
