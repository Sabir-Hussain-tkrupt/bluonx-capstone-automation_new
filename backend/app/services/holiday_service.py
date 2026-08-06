"""Holiday calendar write path + the annual federal seed.

Two things live here.

**Writes.** Admin create/update/delete/range for `holidays`. Authorization is
the router's job (`Depends(require_admin)`); this module owns the DB contract.
Note that every write runs on the service_role key and therefore BYPASSES the
`holidays_*_admin` RLS policies — those protect the frontend's direct Supabase
path only. The application-code admin check is the real gate on this path.

Most rules are enforced by `trg_holidays_guardrails` in the database (past dates
frozen, 25/year, 14 consecutive) and surface as SQLSTATE PT422 with messages
already written for a human. We pass those through verbatim rather than
replacing them with a generic string — they say exactly what the admin needs to
know, and no other layer can reconstruct them.

Two rules the DB does NOT enforce, handled here:
  * Weekends. The trigger permits a Saturday holiday; it is merely pointless
    (weekends are already non-working) and would inflate the contiguous-run
    count against its own cap. Rejected in application code.
  * Duplicates. These surface as a bare 23505 naming the index, which is not
    something to show an admin. Remapped to a 409 naming the date.

**Seed.** `seed_federal_holidays` fills the calendar from the `holidays` package
so it never runs dry. Federal only, no state subdivision: the client is in
Missouri, and Missouri statutory days are state-government closures a private
construction firm does not observe.
"""

from __future__ import annotations

import logging
from datetime import date

import holidays as holidays_pkg
from postgrest.exceptions import APIError
from supabase import Client

from app.core.time import business_today

logger = logging.getLogger(__name__)

# Column is VARCHAR(100).
_MAX_NAME_LEN = 100

_WEEKEND_DETAIL = (
    "Weekends are already non-working days, so adding one has no effect."
)
_GENERIC_DETAIL = "The holiday could not be saved."


class HolidayError(Exception):
    """Raised on holiday-write failure; the router maps it to an HTTPException.
    Mirrors MilestoneError / AwardError / ContractError."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ── Error mapping ───────────────────────────────────────────────────────────


def _has_pt_code(err: APIError, pt: str) -> bool:
    """True when the DB raised SQLSTATE `pt`. Mirrors milestone_service."""
    code = str(getattr(err, "code", "") or "")
    return code == pt or pt in str(err)


def _err_message(err: APIError) -> str | None:
    msg = getattr(err, "message", None)
    return str(msg) if msg else None


def _is_unique_violation(err: APIError) -> bool:
    """Same heuristic as contract_service / award_service (Postgres 23505)."""
    code = getattr(err, "code", None)
    msg = str(err).lower()
    return code == "23505" or "duplicate key" in msg or "unique" in msg


def _map_write_error(err: APIError, *, on_date: date | None = None) -> HolidayError:
    """Translate a holidays-table SQLSTATE into a HolidayError.

    PT422 keeps the DB's message VERBATIM — the guardrail texts ("Year 2027
    already has 25 holidays (max 25). Remove one before adding another.") are
    finished user-facing copy, and the frontend interceptor preserves a string
    `detail` on 422. PT409 (raised by fn_create_holiday_range for a date already
    taken) is likewise already specific. A bare 23505 is not: Postgres names the
    index, so we write that one ourselves.
    """
    if _has_pt_code(err, "PT422"):
        return HolidayError(422, _err_message(err) or _GENERIC_DETAIL)
    if _has_pt_code(err, "PT409"):
        return HolidayError(
            409, _err_message(err) or "That date is already marked as a holiday."
        )
    if _is_unique_violation(err):
        detail = (
            f"{on_date.isoformat()} is already marked as a holiday."
            if on_date
            else "That date is already marked as a holiday."
        )
        return HolidayError(409, detail)
    logger.error("Unexpected holidays write failure: %s", err)
    return HolidayError(422, _GENERIC_DETAIL)


def _reject_weekend(d: date) -> None:
    """Gate a weekend date before any DB round trip. 5 = Saturday, 6 = Sunday."""
    if d.weekday() >= 5:
        raise HolidayError(422, _WEEKEND_DETAIL)


def _first(data) -> dict | None:
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


# ── Writes ──────────────────────────────────────────────────────────────────


def create_holiday(
    *, holiday_date: date, name: str, created_by: str, db: Client
) -> dict:
    """Add one manual holiday.

    `source` is hardcoded 'manual' and `created_by` comes from the authenticated
    admin — neither is client-supplied.
    """
    _reject_weekend(holiday_date)

    try:
        resp = (
            db.table("holidays")
            .insert(
                {
                    "holiday_date": holiday_date.isoformat(),
                    "name": name,
                    "source": "manual",
                    "created_by": str(created_by),
                }
            )
            .execute()
        )
    except APIError as exc:
        raise _map_write_error(exc, on_date=holiday_date) from exc

    row = _first(resp.data)
    if not row:
        raise HolidayError(422, _GENERIC_DETAIL)
    return row


def create_holiday_range(
    *, start_date: date, end_date: date, name: str, created_by: str, db: Client
) -> list[dict]:
    """Add every weekday in [start_date, end_date] as one shutdown, atomically.

    Delegates to the `fn_create_holiday_range` RPC rather than issuing a
    multi-row insert. A multi-row INSERT is one SQL command, so the BEFORE-ROW
    guardrail trigger cannot see the sibling rows of its own batch — the 25/year
    and 14-consecutive caps would silently under-count. The RPC loops row-by-row
    inside one transaction so each row's trigger sees the ones before it, and
    any rejection rolls the whole range back. See the function's comment in the
    schema for the full reasoning.
    """
    try:
        resp = db.rpc(
            "fn_create_holiday_range",
            {
                "p_start": start_date.isoformat(),
                "p_end": end_date.isoformat(),
                "p_name": name,
                "p_created_by": str(created_by),
            },
        ).execute()
    except APIError as exc:
        raise _map_write_error(exc) from exc

    rows = resp.data or []
    if not rows:
        # The RPC raises rather than returning empty, so this is unreachable in
        # practice; treat it as a failure instead of reporting a silent no-op.
        raise HolidayError(422, _GENERIC_DETAIL)
    return rows


def update_holiday(*, holiday_id: str, changes: dict, db: Client) -> dict:
    """Edit a holiday's date and/or name.

    The guardrail trigger blocks editing a row whose existing date is past, and
    blocks moving one into the past.
    """
    if not changes:
        raise HolidayError(400, "No fields to update")

    new_date = changes.get("holiday_date")
    if isinstance(new_date, date):
        _reject_weekend(new_date)
        changes = {**changes, "holiday_date": new_date.isoformat()}

    try:
        resp = (
            db.table("holidays").update(changes).eq("id", str(holiday_id)).execute()
        )
    except APIError as exc:
        raise _map_write_error(exc, on_date=new_date) from exc

    row = _first(resp.data)
    if not row:
        raise HolidayError(404, "Holiday not found")
    return row


def delete_holiday(*, holiday_id: str, db: Client) -> None:
    """Remove a holiday. The guardrail trigger refuses to delete a past one."""
    try:
        resp = db.table("holidays").delete().eq("id", str(holiday_id)).execute()
    except APIError as exc:
        raise _map_write_error(exc) from exc

    if not (resp.data or []):
        raise HolidayError(404, "Holiday not found")


# ── Annual federal seed ─────────────────────────────────────────────────────


def _federal_candidates(years: list[int]) -> list[tuple[date, str]]:
    """US federal observed dates for `years`, weekends removed, deduped by date.

    `observed=True` makes the library emit BOTH the statutory date and its
    observed weekday when the statutory one lands on a weekend (2027 gives both
    Sat Jul 4 and Mon Jul 5). Dropping weekends resolves that to the day the
    office is actually shut, and does so identically across library versions
    that disagree about which entries to emit.
    """
    cal = holidays_pkg.country_holidays("US", years=years, observed=True)

    by_date: dict[date, str] = {}
    for d, name in cal.items():
        if d.weekday() >= 5:
            continue
        if d in by_date:
            continue
        by_date[d] = str(name).strip()[:_MAX_NAME_LEN]

    return sorted(by_date.items())


def seed_federal_holidays(
    db: Client, *, years: list[int], today: date | None = None
) -> dict:
    """Insert any missing US federal holidays for `years` as source='seeded'.

    Idempotent, and deliberately additive only. A date already present is left
    exactly as it is, whatever its source — so an admin who renamed a holiday, or
    added their own on the same day, keeps their row untouched.

    This is why it is select-then-insert rather than an upsert: upserting on
    `holiday_date` would UPDATE on conflict, which both trips the guardrail's
    past-date freeze on older rows and overwrites a manual row's `source`,
    `name`, and `created_by`.

    Past dates are skipped (the guardrail freezes them) and so are weekends.
    Never raises: a single rejected row is recorded and the rest continue, so one
    bad date cannot cost the whole year. Returns a JSON-serializable summary.
    """
    today = today or business_today()
    counts = {
        "years": sorted(years),
        "inserted": 0,
        "skipped_existing": 0,
        "skipped_past": 0,
        "skipped_duplicate": 0,
        "rejected": [],
    }

    candidates = _federal_candidates(years)
    if not candidates:
        return counts

    future = [(d, n) for d, n in candidates if d >= today]
    counts["skipped_past"] = len(candidates) - len(future)
    if not future:
        return counts

    # One read for the whole window; the guardrail caps the table at 25 rows a
    # year, so this stays tiny.
    existing_resp = (
        db.table("holidays")
        .select("holiday_date")
        .gte("holiday_date", future[0][0].isoformat())
        .lte("holiday_date", future[-1][0].isoformat())
        .execute()
    )
    existing = {str(r["holiday_date"]) for r in (existing_resp.data or [])}

    for d, name in future:
        iso = d.isoformat()
        if iso in existing:
            counts["skipped_existing"] += 1
            continue

        # One row per statement so the guardrail trigger counts correctly (the
        # same command-visibility issue fn_create_holiday_range exists for), and
        # so one rejection does not abort the rest of the year.
        try:
            db.table("holidays").insert(
                {
                    "holiday_date": iso,
                    "name": name,
                    "source": "seeded",
                    "created_by": None,
                }
            ).execute()
            counts["inserted"] += 1
        except APIError as exc:
            if _is_unique_violation(exc):
                # Lost a race with an admin adding the same date.
                counts["skipped_duplicate"] += 1
                continue
            reason = _err_message(exc) or str(exc)
            logger.warning("Holiday seed rejected %s (%s): %s", iso, name, reason)
            counts["rejected"].append({"date": iso, "name": name, "reason": reason})

    return counts
