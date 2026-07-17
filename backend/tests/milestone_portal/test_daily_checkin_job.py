"""
Milestone daily check-in job (Phase 10.3).

Driven by FakeDB with the mint + send collaborators patched, so we assert the
job's DECISIONS: which check is due today, never retroactively, never for a
paused/terminal milestone, exactly once per (milestone, alert_type, cycle), and
that a successful send links the alert to its email_log row.

The mint stub deliberately writes the milestone_alerts row the way the real
mint_checkin_token does (row BEFORE send), because that row IS the dedup marker
the idempotency tests exercise.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.jobs import milestone_daily_checkin as job
from app.services.email_service import EmailSendResult
from app.services.milestone_service import MilestoneError

TODAY = date(2026, 7, 15)  # Wed

# Anchors derived from the locked rules (lead 5, min gap 3):
#   progress fires when end == TODAY + 5 AND (end - 5) - start >= 3
PROGRESS_END = TODAY + timedelta(days=5)   # 2026-07-20
START_8_DAY = PROGRESS_END - timedelta(days=8)   # 07-12 -> gap 3, progress DUE
START_7_DAY = PROGRESS_END - timedelta(days=7)   # 07-13 -> gap 2, progress NOT due

_LOG_ID = "log-abc"


@pytest.fixture(autouse=True)
def _patch_clock_and_collaborators(monkeypatch):
    """Freeze the business clock; stub mint + send at the job's import site."""
    monkeypatch.setattr(job, "business_today", lambda: TODAY)

    def _mint(db, *, milestone_id, alert_type, cycle_number):
        # Mirror the real primitive: the alert row lands BEFORE the send.
        db.table("milestone_alerts").insert(
            {
                "milestone_id": milestone_id,
                "alert_type": alert_type,
                "recipient_type": "vendor",
                "cycle_number": cycle_number,
            }
        ).execute()
        return ("raw-token", "https://portal.test/milestone/raw-token")

    mint = _Spy(_mint)
    send = AsyncMock(
        return_value=EmailSendResult(
            message_id="msg-1", status="sent", error=None, log_id=_LOG_ID
        )
    )
    monkeypatch.setattr(job, "mint_checkin_token", mint)
    monkeypatch.setattr(job, "send_milestone_check_email", send)
    return {"mint": mint, "send": send}


class _Spy:
    """Callable that records its calls (mint is sync, so AsyncMock won't do)."""

    def __init__(self, fn):
        self._fn = fn
        self.calls: list[dict] = []

    def __call__(self, db, **kwargs):
        self.calls.append(kwargs)
        return self._fn(db, **kwargs)

    @property
    def alert_types(self) -> list[str]:
        return [c["alert_type"] for c in self.calls]


def _view_row(*, milestone_id, start, end, status="in_progress", cycle=1) -> dict:
    """A v_milestone_overview row (dates arrive as ISO strings from PostgREST)."""
    return {
        "milestone_id": milestone_id,
        "status": status,
        "cycle_number": cycle,
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
    }


def _db(make_db, rows, *, alerts=None, live=None):
    """FakeDB carrying the view rows, their milestones rows, and any prior alerts.

    `live` maps milestone_id -> dict overriding the per-send re-read, so the
    milestone can disagree with the view (rescheduled/completed mid-run).
    """
    live = live or {}
    ms_rows = []
    for r in rows:
        mid = r["milestone_id"]
        ms_rows.append(
            {
                "id": mid,
                "status": r["status"],
                "cycle_number": r["cycle_number"],
                **live.get(mid, {}),
            }
        )
    return make_db(
        {
            "v_milestone_overview": list(rows),
            "milestones": ms_rows,
            "milestone_alerts": list(alerts or []),
        }
    )


async def _run(db):
    return await job.run_milestone_daily_checkin(db, email_service=AsyncMock())


def _sent_types(spy) -> set[str]:
    return set(spy.alert_types)


# ── Due-date logic ─────────────────────────────────────────────────────────


async def test_start_check_fires_on_start_date(make_db, _patch_clock_and_collaborators):
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY + timedelta(days=30))]
    counts = await _run(_db(make_db, rows))

    assert counts["start_sent"] == 1
    assert _sent_types(_patch_clock_and_collaborators["mint"]) == {"start_check"}


async def test_completion_check_fires_on_end_date(make_db, _patch_clock_and_collaborators):
    rows = [_view_row(milestone_id="m1", start=TODAY - timedelta(days=30), end=TODAY)]
    counts = await _run(_db(make_db, rows))

    assert counts["completion_sent"] == 1
    assert _sent_types(_patch_clock_and_collaborators["mint"]) == {"completion_check"}


async def test_progress_check_fires_five_days_before_end(
    make_db, _patch_clock_and_collaborators
):
    rows = [_view_row(milestone_id="m1", start=TODAY - timedelta(days=5), end=PROGRESS_END)]
    counts = await _run(_db(make_db, rows))

    assert counts["progress_sent"] == 1
    assert _sent_types(_patch_clock_and_collaborators["mint"]) == {"progress_check"}


@pytest.mark.parametrize(
    "start,expect_progress",
    [
        (START_7_DAY, False),  # 7-day milestone: no breathing room, no progress check
        (START_8_DAY, True),   # 8-day milestone: exactly enough room
    ],
    ids=["7_day_no_progress", "8_day_gets_progress"],
)
async def test_progress_check_needs_breathing_room(
    make_db, _patch_clock_and_collaborators, start, expect_progress
):
    """The breathing-room gate IS the 'does this need a progress check' test."""
    rows = [_view_row(milestone_id="m1", start=start, end=PROGRESS_END)]
    counts = await _run(_db(make_db, rows))

    assert counts["progress_sent"] == (1 if expect_progress else 0)


async def test_same_day_milestone_gets_start_and_completion(
    make_db, _patch_clock_and_collaborators
):
    """start_date == end_date sends BOTH checks, deliberately.

    They are different questions ("did you start?" / "did you finish?") and, more
    load-bearing, the vendor's completion 'yes' is only legal from in_progress:
    suppressing the start check would strand the milestone in 'scheduled' and 410
    the vendor's answer. See the dedup note in milestone_email_service's docstring.
    """
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY, status="scheduled")]
    counts = await _run(_db(make_db, rows))

    assert _sent_types(_patch_clock_and_collaborators["mint"]) == {
        "start_check",
        "completion_check",
    }
    assert counts["start_sent"] == 1
    assert counts["completion_sent"] == 1
    assert counts["progress_sent"] == 0


async def test_unreadable_dates_skip_the_milestone(
    make_db, _patch_clock_and_collaborators
):
    """start_date/end_date are NOT NULL, so a bad value is corruption: skip it."""
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY)]
    rows[0]["end_date"] = "not-a-date"
    counts = await _run(_db(make_db, rows))

    assert _patch_clock_and_collaborators["mint"].calls == []
    assert counts["start_sent"] == 0


async def test_no_check_due_sends_nothing(make_db, _patch_clock_and_collaborators):
    rows = [
        _view_row(
            milestone_id="m1",
            start=TODAY - timedelta(days=2),
            end=TODAY + timedelta(days=20),
        )
    ]
    counts = await _run(_db(make_db, rows))

    assert counts["start_sent"] == counts["progress_sent"] == counts["completion_sent"] == 0
    assert _patch_clock_and_collaborators["mint"].calls == []


# ── Catch-up guard ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "start,end",
    [
        (TODAY - timedelta(days=3), TODAY + timedelta(days=40)),   # start date passed
        (TODAY - timedelta(days=40), TODAY - timedelta(days=1)),   # end date passed
        (TODAY - timedelta(days=20), TODAY + timedelta(days=4)),   # progress date passed
    ],
    ids=["past_start", "past_end", "past_progress"],
)
async def test_past_check_dates_never_fire_retroactively(
    make_db, _patch_clock_and_collaborators, start, end
):
    """A milestone that materialized mid-window misses the check; no backdated blast."""
    rows = [_view_row(milestone_id="m1", start=start, end=end)]
    counts = await _run(_db(make_db, rows))

    assert _patch_clock_and_collaborators["mint"].calls == []
    assert counts["start_sent"] == counts["progress_sent"] == counts["completion_sent"] == 0


# ── Sendable-state filter ──────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["delayed", "unresponsive", "completed", "cancelled"])
async def test_paused_and_terminal_get_no_checks(
    make_db, _patch_clock_and_collaborators, status
):
    """Paused (delayed/unresponsive) and terminal milestones have a stopped cycle."""
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY, status=status)]
    counts = await _run(_db(make_db, rows))

    assert _patch_clock_and_collaborators["mint"].calls == []
    assert counts["start_sent"] == counts["completion_sent"] == 0


# ── Dedup / idempotency ────────────────────────────────────────────────────


async def test_second_run_same_day_does_not_resend(make_db, _patch_clock_and_collaborators):
    """A coalesced re-fire (or restart) skips on the alert row minted by run one."""
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY + timedelta(days=30))]
    db = _db(make_db, rows)

    first = await _run(db)
    second = await _run(db)

    assert first["start_sent"] == 1
    assert second["start_sent"] == 0
    assert second["skipped_already_sent"] == 1
    assert _patch_clock_and_collaborators["send"].await_count == 1


async def test_existing_alert_for_cycle_blocks_resend(
    make_db, _patch_clock_and_collaborators
):
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY + timedelta(days=30))]
    prior = {
        "id": str(uuid4()),
        "milestone_id": "m1",
        "alert_type": "start_check",
        "recipient_type": "vendor",
        "cycle_number": 1,
    }
    counts = await _run(_db(make_db, rows, alerts=[prior]))

    assert counts["skipped_already_sent"] == 1
    assert _patch_clock_and_collaborators["mint"].calls == []


async def test_cycle_bump_re_enables_checks(make_db, _patch_clock_and_collaborators):
    """After a reschedule the new cycle is eligible; the old cycle's alert can't block it."""
    rows = [
        _view_row(milestone_id="m1", start=TODAY, end=TODAY + timedelta(days=30), cycle=2)
    ]
    stale = {
        "id": str(uuid4()),
        "milestone_id": "m1",
        "alert_type": "start_check",
        "recipient_type": "vendor",
        "cycle_number": 1,
    }
    counts = await _run(_db(make_db, rows, alerts=[stale]))

    assert counts["start_sent"] == 1
    assert _patch_clock_and_collaborators["mint"].calls[0]["cycle_number"] == 2


# ── Per-send re-read ───────────────────────────────────────────────────────


async def test_status_change_between_query_and_send_skips(
    make_db, _patch_clock_and_collaborators
):
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY + timedelta(days=30))]
    db = _db(make_db, rows, live={"m1": {"status": "completed"}})

    counts = await _run(db)

    assert counts["skipped_status_changed"] == 1
    assert _patch_clock_and_collaborators["mint"].calls == []


async def test_cycle_bump_between_query_and_send_skips(
    make_db, _patch_clock_and_collaborators
):
    """The candidate's cycle no longer matches, so its alert_type/cycle is stale."""
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY + timedelta(days=30))]
    db = _db(make_db, rows, live={"m1": {"cycle_number": 2}})

    counts = await _run(db)

    assert counts["skipped_status_changed"] == 1
    assert _patch_clock_and_collaborators["mint"].calls == []


# ── email_log linkage (the point of Part A) ────────────────────────────────


async def test_successful_send_stamps_email_log_id(make_db, _patch_clock_and_collaborators):
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY + timedelta(days=30))]
    db = _db(make_db, rows)

    await _run(db)

    alert = db.tables["milestone_alerts"][0]
    assert alert["email_log_id"] == _LOG_ID


async def test_failed_send_still_links_its_log_row(make_db, _patch_clock_and_collaborators):
    """A 'failed' log is an undelivered status to the no-response job, so link it."""
    _patch_clock_and_collaborators["send"].return_value = EmailSendResult(
        message_id="", status="failed", error="boom", log_id="log-failed"
    )
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY + timedelta(days=30))]
    db = _db(make_db, rows)

    counts = await _run(db)

    assert counts["failed"] == 1
    alert = db.tables["milestone_alerts"][0]
    assert alert["email_log_id"] == "log-failed"


async def test_send_failure_keeps_the_alert_row(make_db, _patch_clock_and_collaborators):
    """The alert row is the dedup marker; a failed send must not delete it."""
    _patch_clock_and_collaborators["send"].return_value = None
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY + timedelta(days=30))]
    db = _db(make_db, rows)

    counts = await _run(db)

    assert counts["failed"] == 1
    assert len(db.tables["milestone_alerts"]) == 1
    assert db.tables["milestone_alerts"][0].get("email_log_id") is None


# ── Failure isolation ──────────────────────────────────────────────────────


async def test_mint_failure_is_counted_not_raised(make_db, _patch_clock_and_collaborators):
    """No contract vendor / no primary contact must not sink the batch."""

    def _boom(db, **kwargs):
        raise MilestoneError(422, "Vendor has no primary contact")

    _patch_clock_and_collaborators["mint"]._fn = _boom
    rows = [_view_row(milestone_id="m1", start=TODAY, end=TODAY + timedelta(days=30))]

    counts = await _run(_db(make_db, rows))

    assert counts["failed"] == 1
    _patch_clock_and_collaborators["send"].assert_not_awaited()


async def test_one_bad_milestone_does_not_stop_the_others(
    make_db, _patch_clock_and_collaborators
):
    rows = [
        _view_row(milestone_id="m1", start=TODAY, end=TODAY + timedelta(days=30)),
        _view_row(milestone_id="m2", start=TODAY, end=TODAY + timedelta(days=30)),
    ]
    send = _patch_clock_and_collaborators["send"]
    send.side_effect = [
        RuntimeError("provider exploded"),
        EmailSendResult(message_id="m", status="sent", error=None, log_id=_LOG_ID),
    ]

    counts = await _run(_db(make_db, rows))

    assert counts["failed"] == 1
    assert counts["start_sent"] == 1
