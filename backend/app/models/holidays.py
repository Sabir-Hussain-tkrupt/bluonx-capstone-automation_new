"""Holiday calendar schemas — org-wide non-working days.

The field is `holiday_date`, matching the column. The frontend's `Holiday` type
calls it `date` and maps at its own boundary; it has to map regardless, because
its direct Supabase reads return the column name too.

`source` is deliberately absent from every write model: provenance is a system
fact (who wrote the row — the annual seed or an admin), not something a request
gets to assert.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.common import BluOnXBase

# Sanity ceiling on a single range request. The DB's 14-consecutive-day guardrail
# is the real limit and rejects anything close to this; this only stops a
# fat-fingered range from being sent at all.
MAX_RANGE_SPAN_DAYS = 31


def _clean_name(v: str | None) -> str | None:
    """Trim, then reject blank.

    The DB's CHECK (btrim(name) <> '') is a backstop, not the gate — a
    whitespace-only name should fail as a readable validation error, not as a
    23514 the client has to decode.
    """
    if v is None:
        return None
    cleaned = v.strip()
    if not cleaned:
        raise ValueError("Holiday name cannot be blank.")
    return cleaned


class HolidayCreate(BluOnXBase):
    holiday_date: date
    name: str = Field(min_length=1, max_length=100)

    _clean = field_validator("name")(_clean_name)


class HolidayRangeCreate(BluOnXBase):
    """A multi-day shutdown. Weekends inside the range are skipped, not rejected."""

    start_date: date
    end_date: date
    name: str = Field(min_length=1, max_length=100)

    _clean = field_validator("name")(_clean_name)

    @model_validator(mode="after")
    def _check_span(self) -> "HolidayRangeCreate":
        if self.end_date < self.start_date:
            raise ValueError("The end date cannot be before the start date.")
        if (self.end_date - self.start_date).days + 1 > MAX_RANGE_SPAN_DAYS:
            raise ValueError(
                f"A holiday range cannot span more than {MAX_RANGE_SPAN_DAYS} days."
            )
        return self


class HolidayUpdate(BluOnXBase):
    holiday_date: date | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)

    _clean = field_validator("name")(_clean_name)


class HolidayResponse(BluOnXBase):
    id: UUID
    holiday_date: date
    name: str
    source: str
    # NULL on seeded rows: no human actor.
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
