"""Holiday calendar endpoints — /api/v1/holidays

Writes only. Reads stay on the frontend's direct Supabase path, protected by the
`holidays_select_authenticated` RLS policy — any active user may read the
calendar, so there is nothing for an endpoint here to add.

Every write is `Depends(require_admin)`, and that is load-bearing rather than
decorative: these handlers hold the service_role key, which bypasses RLS
entirely, so the `holidays_*_admin` policies do not defend this path. The route
guard on /settings/calendar is cosmetic; this check is the real gate.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.core.auth import require_admin
from app.core.supabase_client import get_supabase
from app.models.holidays import (
    HolidayCreate,
    HolidayRangeCreate,
    HolidayResponse,
    HolidayUpdate,
)
from app.services import holiday_service
from app.services.holiday_service import HolidayError

router = APIRouter()


@router.post(
    "/holidays", response_model=HolidayResponse, status_code=status.HTTP_201_CREATED
)
async def create_holiday(
    payload: HolidayCreate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Add one holiday (admin only)."""
    try:
        return holiday_service.create_holiday(
            holiday_date=payload.holiday_date,
            name=payload.name,
            created_by=user["user_id"],
            db=db,
        )
    except HolidayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post(
    "/holidays/range",
    response_model=list[HolidayResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_holiday_range(
    payload: HolidayRangeCreate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Add a multi-day shutdown (admin only).

    Weekends inside the range are skipped silently. All-or-nothing: if any day
    trips a guardrail, nothing is written.
    """
    try:
        return holiday_service.create_holiday_range(
            start_date=payload.start_date,
            end_date=payload.end_date,
            name=payload.name,
            created_by=user["user_id"],
            db=db,
        )
    except HolidayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.patch("/holidays/{holiday_id}", response_model=HolidayResponse)
async def update_holiday(
    holiday_id: UUID,
    payload: HolidayUpdate,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Edit a holiday's date or name (admin only)."""
    try:
        return holiday_service.update_holiday(
            holiday_id=str(holiday_id),
            changes=payload.model_dump(exclude_unset=True),
            db=db,
        )
    except HolidayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holiday(
    holiday_id: UUID,
    user: dict = Depends(require_admin),
    db: Client = Depends(get_supabase),
):
    """Remove a holiday (admin only). Past holidays are frozen by the DB."""
    try:
        holiday_service.delete_holiday(holiday_id=str(holiday_id), db=db)
    except HolidayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
