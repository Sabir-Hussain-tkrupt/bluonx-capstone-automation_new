"""
Manual-testing helper (Phase 10.2): mint a milestone check-in token and print the
portal URL to open in the browser.

There is no HTTP mint endpoint yet (that is the Phase 10.3 daily send job), so this
stands in for it during manual verification of the vendor check-in flow.

Usage (from backend/, with the venv):
    python scripts/mint_checkin.py                       # auto-pick a milestone
    python scripts/mint_checkin.py <milestone_id>        # a specific milestone
    python scripts/mint_checkin.py <milestone_id> start  # start | progress | completion
"""

from __future__ import annotations

import sys

from app.core.config import settings
from app.core.supabase_client import init_supabase
from app.services.milestone_token_service import mint_checkin_token

_CHECK_TO_ALERT = {
    "start": "start_check",
    "progress": "progress_check",
    "completion": "completion_check",
}


def _pick_milestone(db) -> str | None:
    """First scheduled/in_progress milestone whose contract has a primary contact."""
    rows = (
        db.table("milestones")
        .select("id, contract_id")
        .in_("status", ["scheduled", "in_progress"])
        .limit(50)
        .execute()
        .data
        or []
    )
    for m in rows:
        c = (
            db.table("contracts")
            .select("vendor_id")
            .eq("id", m["contract_id"])
            .single()
            .execute()
            .data
        )
        if not c:
            continue
        pc = (
            db.table("vendor_contacts")
            .select("id")
            .eq("vendor_id", c["vendor_id"])
            .eq("is_primary", True)
            .limit(1)
            .execute()
            .data
        )
        if pc:
            return m["id"]
    return None


def main() -> None:
    db = init_supabase(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    milestone_id = sys.argv[1] if len(sys.argv) > 1 else _pick_milestone(db)
    if not milestone_id:
        raise SystemExit(
            "No scheduled/in_progress milestone with a contract + primary contact "
            "found. Create one first, or pass a milestone id."
        )

    check = sys.argv[2] if len(sys.argv) > 2 else "progress"
    if check not in _CHECK_TO_ALERT:
        raise SystemExit(f"check must be one of {list(_CHECK_TO_ALERT)}")

    ms = (
        db.table("milestones")
        .select("name, status, cycle_number")
        .eq("id", milestone_id)
        .single()
        .execute()
        .data
    )
    raw, url = mint_checkin_token(
        db,
        milestone_id=milestone_id,
        alert_type=_CHECK_TO_ALERT[check],
        cycle_number=ms["cycle_number"],
    )

    print(f"milestone : {ms.get('name')} ({ms.get('status')}, cycle {ms.get('cycle_number')})")
    print(f"check     : {check} ({_CHECK_TO_ALERT[check]})")
    print(f"raw token : {raw}")
    print()
    print("Open this in the portal:")
    print(f"  {url}")


if __name__ == "__main__":
    main()
