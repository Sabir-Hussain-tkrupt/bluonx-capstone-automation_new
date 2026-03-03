"""Bid package endpoints — /api/v1/bid-packages"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.bids import (
    BidPackageCreate,
    BidPackageDocumentCreate,
    BidPackageDocumentResponse,
    BidPackageResponse,
    BidPackageUpdate,
)

router = APIRouter()


@router.get("/bid-packages", response_model=list[BidPackageResponse])
async def list_bid_packages(
    task_id: UUID | None = None,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List bid packages, optionally filtered by task_id."""
    # TODO: Implement in later phase
    return []


@router.get("/bid-packages/{bid_package_id}", response_model=BidPackageResponse)
async def get_bid_package(
    bid_package_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single bid package by ID."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/bid-packages", response_model=BidPackageResponse, status_code=status.HTTP_201_CREATED)
async def create_bid_package(
    bid_package: BidPackageCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new bid package for a task."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/bid-packages/{bid_package_id}", response_model=BidPackageResponse)
async def update_bid_package(
    bid_package_id: UUID,
    bid_package: BidPackageUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a bid package."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/bid-packages/{bid_package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bid_package(
    bid_package_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Cancel a bid package."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


# ── Bid Package Documents ────────────────────────────────────────────────


@router.get(
    "/bid-packages/{bid_package_id}/documents",
    response_model=list[BidPackageDocumentResponse],
)
async def list_bid_package_documents(
    bid_package_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List documents attached to a bid package."""
    # TODO: Implement in later phase
    return []


@router.post(
    "/bid-packages/{bid_package_id}/documents",
    response_model=BidPackageDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attach_document_to_bid_package(
    bid_package_id: UUID,
    document: BidPackageDocumentCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Attach a project document to a bid package."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete(
    "/bid-packages/{bid_package_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_document_from_bid_package(
    bid_package_id: UUID,
    document_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Remove a document from a bid package."""
    # TODO: Implement in later phase
    raise HTTPException(status_code=501, detail="Not implemented")
