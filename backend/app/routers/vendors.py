"""Vendor endpoints — /api/v1/vendors"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.vendors import (
    VendorBulkTradeCreate,
    VendorContactCreateInline,
    VendorContactResponse,
    VendorContactUpdate,
    VendorCreate,
    VendorDetailResponse,
    VendorDocumentCreate,
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

    response = db.table("vendors").insert(vendor_data).execute()

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
    _get_vendor_or_404(db, vendor_id)

    update_data = vendor.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    # Convert Decimal fields to string for JSON serialization
    for key in ("insurance_coverage_amount", "bonding_capacity", "latitude", "longitude"):
        if key in update_data and update_data[key] is not None:
            update_data[key] = str(update_data[key])

    # Convert date fields to string
    if "insurance_expiration_date" in update_data and update_data["insurance_expiration_date"] is not None:
        update_data["insurance_expiration_date"] = update_data["insurance_expiration_date"].isoformat()

    response = (
        db.table("vendors")
        .update(update_data)
        .eq("id", str(vendor_id))
        .execute()
    )

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


@router.post(
    "/vendors/{vendor_id}/documents",
    response_model=VendorDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_vendor_document(
    vendor_id: UUID,
    document: VendorDocumentCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Upload a document for a vendor."""
    _get_vendor_or_404(db, vendor_id)

    doc_data = document.model_dump()
    doc_data["vendor_id"] = str(vendor_id)
    doc_data["uploaded_by"] = user["user_id"]

    if doc_data.get("expiration_date") is not None:
        doc_data["expiration_date"] = doc_data["expiration_date"].isoformat()

    response = db.table("vendor_documents").insert(doc_data).execute()

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to upload document",
        )

    return response.data[0]


@router.delete("/vendors/{vendor_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor_document(
    vendor_id: UUID,
    document_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a vendor document."""
    _get_vendor_or_404(db, vendor_id)

    response = (
        db.table("vendor_documents")
        .delete()
        .eq("id", str(document_id))
        .eq("vendor_id", str(vendor_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )


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
