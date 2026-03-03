"""Vendor endpoints — /api/v1/vendors"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.vendors import (
    VendorCreate,
    VendorContactCreate,
    VendorContactResponse,
    VendorContactUpdate,
    VendorDocumentCreate,
    VendorDocumentResponse,
    VendorResponse,
    VendorTradeCreate,
    VendorTradeResponse,
    VendorUpdate,
)

router = APIRouter()


# ── Vendors CRUD ─────────────────────────────────────────────────────────


@router.get("/vendors", response_model=list[VendorResponse])
async def list_vendors(
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List all active vendors."""
    # TODO: Implement in Phase 3
    return []


@router.get("/vendors/{vendor_id}", response_model=VendorResponse)
async def get_vendor(
    vendor_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single vendor by ID."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/vendors", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    vendor: VendorCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new vendor."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/vendors/{vendor_id}", response_model=VendorResponse)
async def update_vendor(
    vendor_id: UUID,
    vendor: VendorUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a vendor."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/vendors/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor(
    vendor_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Soft-delete a vendor (sets deleted_at)."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


# ── Vendor Contacts ──────────────────────────────────────────────────────


@router.get("/vendors/{vendor_id}/contacts", response_model=list[VendorContactResponse])
async def list_vendor_contacts(
    vendor_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List contacts for a vendor."""
    # TODO: Implement in Phase 3
    return []


@router.post(
    "/vendors/{vendor_id}/contacts",
    response_model=VendorContactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_vendor_contact(
    vendor_id: UUID,
    contact: VendorContactCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Add a contact to a vendor."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/vendors/{vendor_id}/contacts/{contact_id}", response_model=VendorContactResponse)
async def update_vendor_contact(
    vendor_id: UUID,
    contact_id: UUID,
    contact: VendorContactUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a vendor contact."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/vendors/{vendor_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor_contact(
    vendor_id: UUID,
    contact_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a vendor contact."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


# ── Vendor Trades ────────────────────────────────────────────────────────


@router.get("/vendors/{vendor_id}/trades", response_model=list[VendorTradeResponse])
async def list_vendor_trades(
    vendor_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List trade associations for a vendor."""
    # TODO: Implement in Phase 3
    return []


@router.post(
    "/vendors/{vendor_id}/trades",
    response_model=VendorTradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_vendor_trade(
    vendor_id: UUID,
    vendor_trade: VendorTradeCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Associate a trade with a vendor."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/vendors/{vendor_id}/trades/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_vendor_trade(
    vendor_id: UUID,
    trade_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Remove a trade association from a vendor."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


# ── Vendor Documents ─────────────────────────────────────────────────────


@router.get("/vendors/{vendor_id}/documents", response_model=list[VendorDocumentResponse])
async def list_vendor_documents(
    vendor_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List documents for a vendor."""
    # TODO: Implement in Phase 3
    return []


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
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/vendors/{vendor_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor_document(
    vendor_id: UUID,
    document_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a vendor document."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")
