"""Trade endpoints — /api/v1/trades"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.core.auth import get_current_active_user, require_admin
from app.core.supabase_client import get_supabase
from app.models.trades import TradeCreate, TradeResponse, TradeUpdate

router = APIRouter()


@router.get("/trades", response_model=list[TradeResponse])
async def list_trades(
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    phase: str | None = Query(default=None, description="Filter by phase"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List all trades, optionally filtered by active status and phase."""
    query = db.table("trades").select("*")

    if is_active is not None:
        query = query.eq("is_active", is_active)

    if phase:
        query = query.eq("phase", phase)

    query = query.order("phase").order("name")

    response = query.execute()

    return response.data or []


@router.get("/trades/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single trade by ID."""
    response = (
        db.table("trades")
        .select("*")
        .eq("id", str(trade_id))
        .single()
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found",
        )

    return response.data


@router.post("/trades", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def create_trade(
    trade: TradeCreate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Create a new trade (admin only)."""
    response = (
        db.table("trades")
        .insert(trade.model_dump())
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create trade",
        )

    return response.data[0]


@router.patch("/trades/{trade_id}", response_model=TradeResponse)
async def update_trade(
    trade_id: UUID,
    trade: TradeUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Update a trade (admin only)."""
    update_data = trade.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    response = (
        db.table("trades")
        .update(update_data)
        .eq("id", str(trade_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found",
        )

    return response.data[0]


@router.delete("/trades/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trade(
    trade_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Deactivate a trade (admin only). Sets is_active to false."""
    response = (
        db.table("trades")
        .update({"is_active": False})
        .eq("id", str(trade_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found",
        )
