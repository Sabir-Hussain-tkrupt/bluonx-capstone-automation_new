"""
Seed the holiday calendar from the US federal calendar.

This is the bootstrap path (filling an empty table for the first time) and the
recovery path (a missed annual run — see app/jobs/holiday_seed.py, which calls
the same service function on January 2).

Idempotent and additive only: a date already in the table is left exactly as it
is, whatever its source, so an admin's manual rows and renames survive. Past
dates and weekends are skipped.

Usage (from backend/, with the venv). Run it as a MODULE, not as a path — the
path form puts scripts/ on sys.path instead of backend/, so `app` is unimportable:
    python -m scripts.seed_holidays                    # this year + next
    python -m scripts.seed_holidays --years 2026 2027
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import settings
from app.core.supabase_client import init_supabase
from app.core.time import business_today
from app.services.holiday_service import seed_federal_holidays


def main() -> int:
    today = business_today()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=[today.year, today.year + 1],
        help="Calendar years to seed (default: this year and next).",
    )
    args = parser.parse_args()

    # The module-level get_supabase_client() requires the FastAPI lifespan, which
    # is not running here.
    db = init_supabase(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    result = seed_federal_holidays(db, years=args.years, today=today)

    print(f"Years:            {result['years']}")
    print(f"Inserted:         {result['inserted']}")
    print(f"Already present:  {result['skipped_existing']}")
    print(f"Skipped (past):   {result['skipped_past']}")
    print(f"Skipped (dupe):   {result['skipped_duplicate']}")

    if result["rejected"]:
        print(f"\nRejected ({len(result['rejected'])}):")
        for row in result["rejected"]:
            print(f"  {row['date']}  {row['name']}: {row['reason']}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
