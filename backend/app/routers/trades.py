"""Trade endpoints — /api/v1/trades

Trades can have subtrades (one level). Rules, enforced in the database
(migration 20261117) and surfaced here with readable messages:

* a subtrade always carries its parent's phase;
* a trade that has subtrades is assigned through one of them;
* a trade or subtrade can be renamed / re-phased only while nothing uses it,
  and deleted only while nothing uses it and it has no subtrades.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.exceptions import APIError
from supabase import Client

from app.core.auth import get_current_active_user, require_admin
from app.core.supabase_client import get_supabase
from app.models.trades import TradeCreate, TradeResponse, TradeUpdate, TradeUsage
from app.services.financial_errors import to_financial_error

router = APIRouter()

_USAGE_KEYS = (
    "tasks",
    "vendors",
    "task_templates",
    "bid_templates",
    "budget_template_lines",
    "variances",
    "subtrades",
)


def _load_trade(db: Client, trade_id: UUID | str) -> dict:
    response = (
        db.table("trades")
        .select("*")
        .eq("id", str(trade_id))
        .maybe_single()
        .execute()
    )
    if not response or not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found",
        )
    return response.data


def _usage(db: Client, trade_id: UUID | str) -> TradeUsage:
    try:
        resp = db.rpc("fn_trade_usage", {"p_trade_id": str(trade_id)}).execute()
    except APIError as exc:
        err = to_financial_error(exc, "Could not check where this trade is used.")
        raise HTTPException(status_code=err.status_code, detail=err.detail) from exc
    data = resp.data if resp is not None else None
    if isinstance(data, list):
        data = data[0] if data else None
    data = data or {}
    counts = {k: int(data.get(k) or 0) for k in _USAGE_KEYS}
    records = sum(v for k, v in counts.items() if k != "subtrades")
    total = int(data.get("total") or sum(counts.values()))
    return TradeUsage(
        trade_id=trade_id,
        **counts,
        total=total,
        in_use=records > 0,
        can_edit=records == 0,
        can_delete=total == 0,
    )


def describe_usage(usage: TradeUsage) -> str:
    labels = {
        "tasks": ("task", "tasks"),
        "vendors": ("vendor", "vendors"),
        "task_templates": ("task template", "task templates"),
        "bid_templates": ("bid template", "bid templates"),
        "budget_template_lines": ("budget template line", "budget template lines"),
        "variances": ("variance", "variances"),
        "subtrades": ("subtrade", "subtrades"),
    }
    parts = []
    for key, (one, many) in labels.items():
        n = getattr(usage, key)
        if n:
            parts.append(f"{n} {one if n == 1 else many}")
    return ", ".join(parts)


@router.get("/trades", response_model=list[TradeResponse])
async def list_trades(
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    phase: str | None = Query(default=None, description="Filter by phase"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List all trades and subtrades, optionally filtered by active status and phase."""
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
    return _load_trade(db, trade_id)


@router.get("/trades/{trade_id}/usage", response_model=TradeUsage)
async def get_trade_usage(
    trade_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Where a trade is used, and whether it can be edited or deleted."""
    _load_trade(db, trade_id)
    return _usage(db, trade_id)


@router.post("/trades", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def create_trade(
    trade: TradeCreate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Create a trade, or a subtrade when `parent_trade_id` is given (admin only)."""
    payload = trade.model_dump(mode="json")

    if trade.parent_trade_id is not None:
        parent = _load_trade(db, trade.parent_trade_id)
        if parent.get("parent_trade_id"):
            raise HTTPException(
                status_code=422,
                detail=f'"{parent["name"]}" is already a subtrade; subtrades cannot have their own subtrades.',
            )
        # The database copies the parent's phase anyway; sending it keeps the
        # insert valid on its own.
        payload["phase"] = parent["phase"]
    else:
        payload.pop("parent_trade_id", None)

    response = db.table("trades").insert(payload).execute()

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
    """Update a trade (admin only).

    Name and phase can change only while nothing uses the trade. Turning a
    trade on or off (`is_active`) is always allowed.
    """
    update_data = trade.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    current = _load_trade(db, trade_id)

    if "phase" in update_data and current.get("parent_trade_id"):
        if update_data["phase"] != current.get("phase"):
            raise HTTPException(
                status_code=422,
                detail="A subtrade always uses its parent trade's phase. Change the parent trade's phase instead.",
            )
        update_data.pop("phase")

    changes_identity = any(
        key in update_data and update_data[key] != current.get(key)
        for key in ("name", "phase")
    )
    if changes_identity:
        usage = _usage(db, trade_id)
        if not usage.can_edit:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f'"{current["name"]}" cannot be changed because it is in use '
                    f"({describe_usage(usage)})."
                ),
            )

    if not update_data:
        return current

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
    """Delete a trade or subtrade (admin only).

    Refused (409) while any task, vendor, template or variance uses it, or
    while it still has subtrades. To retire a used trade, set `is_active` to
    false with PATCH instead.
    """
    current = _load_trade(db, trade_id)
    usage = _usage(db, trade_id)
    if not usage.can_delete:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f'"{current["name"]}" cannot be deleted because it is in use '
                f"({describe_usage(usage)})."
            ),
        )

    # The database re-checks under a row lock, so a race still cannot delete a
    # trade that became used a moment ago.
    try:
        db.rpc("fn_delete_trade", {"p_trade_id": str(trade_id)}).execute()
    except APIError as exc:
        err = to_financial_error(exc, "Failed to delete trade.")
        raise HTTPException(status_code=err.status_code, detail=err.detail) from exc
