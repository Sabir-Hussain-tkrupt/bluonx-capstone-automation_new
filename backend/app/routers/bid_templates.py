"""Bid Template endpoints — /api/v1/bid-templates"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.exceptions import APIError
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.models.bid_templates import (
    BidTemplateCreate,
    BidTemplateDetailResponse,
    BidTemplateListResponse,
    BidTemplateUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────


def _parse_uuid(value: str, field_name: str = "id") -> UUID:
    """Parse a string as UUID, raise 400 if invalid."""
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}: '{value}' is not a valid UUID",
        )


def _get_template_or_404(db: Client, template_id: UUID) -> dict:
    """Fetch a bid template by ID, raise 404 if not found."""
    try:
        response = (
            db.table("bid_templates")
            .select("*")
            .eq("id", str(template_id))
            .single()
            .execute()
        )
    except APIError as exc:
        # .single() throws when 0 rows found
        if "PGRST116" in str(getattr(exc, "code", "")) or "0 rows" in str(getattr(exc, "message", "")):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bid template not found",
            ) from exc
        logger.error("Supabase query failed for bid_templates: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch bid template from database",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bid template not found",
        )
    return response.data


def _build_template_response(db: Client, template: dict) -> dict:
    """Enrich a template dict with trade_name and item_count."""
    trade_name = None
    if template.get("trade_id"):
        try:
            trade_resp = (
                db.table("trades")
                .select("name")
                .eq("id", template["trade_id"])
                .single()
                .execute()
            )
            if trade_resp.data:
                trade_name = trade_resp.data["name"]
        except APIError as exc:
            logger.warning("Failed to fetch trade name for %s: %s", template["trade_id"], exc)

    try:
        items_resp = (
            db.table("bid_template_items")
            .select("id", count="exact")
            .eq("bid_template_id", template["id"])
            .execute()
        )
        item_count = items_resp.count or 0
    except APIError as exc:
        logger.warning("Failed to count items for template %s: %s", template["id"], exc)
        item_count = 0

    return {
        **template,
        "trade_name": trade_name,
        "item_count": item_count,
    }


def _build_detail_response(db: Client, template: dict) -> dict:
    """Enrich a template dict with trade_name and full items list."""
    trade_name = None
    if template.get("trade_id"):
        try:
            trade_resp = (
                db.table("trades")
                .select("name")
                .eq("id", template["trade_id"])
                .single()
                .execute()
            )
            if trade_resp.data:
                trade_name = trade_resp.data["name"]
        except APIError as exc:
            logger.warning("Failed to fetch trade name for %s: %s", template["trade_id"], exc)

    try:
        items_resp = (
            db.table("bid_template_items")
            .select("*")
            .eq("bid_template_id", template["id"])
            .order("sort_order")
            .execute()
        )
        items = items_resp.data or []
    except APIError as exc:
        logger.warning("Failed to fetch items for template %s: %s", template["id"], exc)
        items = []

    return {
        **template,
        "trade_name": trade_name,
        "item_count": len(items),
        "items": items,
    }


def _validate_trade_id(db: Client, trade_id: UUID) -> None:
    """Verify trade_id references an existing trade."""
    try:
        resp = (
            db.table("trades")
            .select("id")
            .eq("id", str(trade_id))
            .single()
            .execute()
        )
    except APIError as exc:
        logger.error("Failed to validate trade_id %s: %s", trade_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to validate trade",
        ) from exc

    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Trade not found",
        )


def _insert_items(db: Client, template_id: str, items: list) -> None:
    """Bulk insert bid_template_items with sort_order based on position."""
    if not items:
        return
    rows = []
    for idx, item in enumerate(items):
        row = item.model_dump()
        row["bid_template_id"] = template_id
        row["sort_order"] = idx
        rows.append(row)
    try:
        db.table("bid_template_items").insert(rows).execute()
    except APIError as exc:
        logger.error("Failed to insert bid_template_items: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to create template items: {exc.message}",
        ) from exc


# ── CRUD ────────────────────────────────────────────────────────────────


@router.get("/bid-templates", response_model=BidTemplateListResponse)
async def list_bid_templates(
    search: str | None = Query(default=None, description="Search by template name"),
    trade_id: str | None = Query(default=None, description="Filter by trade_id, or 'null' for general-purpose"),
    sort_by: str = Query(default="name", description="Column to sort by"),
    sort_dir: str = Query(default="asc", description="Sort direction: asc or desc"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List all bid templates with search, trade filter, sort, and pagination."""

    # Validate trade_id format before sending to Postgres
    if trade_id and trade_id != "null":
        _parse_uuid(trade_id, "trade_id")

    query = db.table("bid_templates").select("*", count="exact")

    if search:
        query = query.ilike("name", f"%{search}%")

    if trade_id == "null":
        query = query.is_("trade_id", "null")
    elif trade_id:
        query = query.eq("trade_id", trade_id)

    # Sorting — whitelist to prevent injection
    allowed_sort_columns = {"name", "is_lump_sum", "created_at", "updated_at"}
    if sort_by not in allowed_sort_columns:
        sort_by = "name"
    ascending = sort_dir.lower() != "desc"
    query = query.order(sort_by, desc=not ascending)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    try:
        response = query.execute()
    except APIError as exc:
        logger.error("Supabase query failed for bid_templates list: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch bid templates from database",
        ) from exc

    templates = response.data or []

    # Enrich each template with trade_name and item_count
    enriched = []
    for t in templates:
        enriched.append(_build_template_response(db, t))

    return BidTemplateListResponse(
        items=enriched,
        total=response.count or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/bid-templates/{template_id}", response_model=BidTemplateDetailResponse)
async def get_bid_template(
    template_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single bid template with all its items."""
    template = _get_template_or_404(db, template_id)
    return _build_detail_response(db, template)


@router.post(
    "/bid-templates",
    response_model=BidTemplateDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bid_template(
    body: BidTemplateCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new bid template with inline items."""

    # Validate trade_id if provided
    if body.trade_id:
        _validate_trade_id(db, body.trade_id)

    # Build template data
    template_data = body.model_dump(exclude={"items"})
    template_data["created_by"] = user["user_id"]
    if template_data.get("trade_id"):
        template_data["trade_id"] = str(template_data["trade_id"])

    try:
        resp = db.table("bid_templates").insert(template_data).execute()
    except APIError as exc:
        logger.error("Supabase insert failed for bid_templates: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Database rejected the data: {exc.message}",
        ) from exc

    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create bid template",
        )

    new_template = resp.data[0]

    # Insert items
    _insert_items(db, new_template["id"], body.items)

    return _build_detail_response(db, new_template)


@router.put("/bid-templates/{template_id}", response_model=BidTemplateDetailResponse)
async def update_bid_template(
    template_id: UUID,
    body: BidTemplateUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a bid template's metadata and replace all items."""

    _get_template_or_404(db, template_id)

    # Validate trade_id if provided
    if body.trade_id:
        _validate_trade_id(db, body.trade_id)

    # Update metadata
    update_data = body.model_dump(exclude={"items"})
    if update_data.get("trade_id"):
        update_data["trade_id"] = str(update_data["trade_id"])

    try:
        db.table("bid_templates").update(update_data).eq("id", str(template_id)).execute()
    except APIError as exc:
        logger.error("Supabase update failed for bid_templates: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Database rejected the data: {exc.message}",
        ) from exc

    # Replace items: delete all existing, insert new
    try:
        db.table("bid_template_items").delete().eq(
            "bid_template_id", str(template_id)
        ).execute()
    except APIError as exc:
        logger.error("Failed to delete old items for template %s: %s", template_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to replace template items",
        ) from exc

    _insert_items(db, str(template_id), body.items)

    # Fetch updated template for response
    updated = _get_template_or_404(db, template_id)
    return _build_detail_response(db, updated)


@router.delete("/bid-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bid_template(
    template_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a bid template. Fails with 409 if referenced by bid packages."""

    _get_template_or_404(db, template_id)

    try:
        db.table("bid_templates").delete().eq("id", str(template_id)).execute()
    except APIError as exc:
        # FK violation from bid_packages.bid_template_id ON DELETE RESTRICT
        if "23503" in str(exc.code) or "violates foreign key" in str(exc.message).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This template is in use by one or more bid packages and cannot be deleted.",
            ) from exc
        logger.error("Supabase delete failed for bid_templates: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to delete template: {exc.message}",
        ) from exc
