"""`context_from_row` must anchor `today` to UTC (Task 9.1 hardening).

The insurance-expired BLOCK compares the cert date against `context.today`, and
the result snapshot stamps `validated_at` in UTC. If `today` came from the
server's local clock, a cert expiring "today" could be judged on the wrong
calendar day at the midnight boundary on a non-UTC host — for a non-overridable
block that's a real off-by-one. `today` must derive from the same UTC clock.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from app.services.pre_award_validation_service import context_from_row

# Minimal chain row — only the fields context_from_row reads, none date-bearing
# so the parse helpers don't interfere with the clock under test.
_ROW = {
    "total_amount": "100000.00",
    "is_superseded": False,
    "is_draft": False,
    "status": "submitted",
    "vendors": {"current_active_jobs": 0},
    "bid_invitations": {"bid_packages": {"tasks": {"projects": {}}}},
}


def test_today_is_utc_not_local_clock():
    sentinel = date(2026, 1, 1)
    with patch(
        "app.services.pre_award_validation_service._utc_today",
        return_value=sentinel,
    ):
        ctx = context_from_row(_ROW)
    assert ctx.today == sentinel
