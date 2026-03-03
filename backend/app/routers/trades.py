"""Trade endpoints — /api/v1/trades"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import get_current_active_user, require_admin
from app.core.supabase_client import get_supabase
from app.models.trades import TradeCreate, TradeResponse, TradeUpdate

router = APIRouter()


@router.get("/trades", response_model=list[TradeResponse])
async def list_trades(
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List all trades."""
    # TODO: Implement in Phase 3
    return []


@router.get("/trades/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single trade by ID."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/trades", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def create_trade(
    trade: TradeCreate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Create a new trade (admin only)."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/trades/{trade_id}", response_model=TradeResponse)
async def update_trade(
    trade_id: UUID,
    trade: TradeUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Update a trade (admin only)."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/trades/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trade(
    trade_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Deactivate a trade (admin only)."""
    # TODO: Implement in Phase 3
    raise HTTPException(status_code=501, detail="Not implemented")
