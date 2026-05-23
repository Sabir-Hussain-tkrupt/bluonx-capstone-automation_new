"""Tests for run_daily_bid_reminders — the daily bid-reminders job body.

The job body is exercised directly with FakeReminderDB (see conftest.py) and
an AsyncMock EmailService. The real template_renderer is used so the edited
bid_reminder_* templates are genuinely rendered — a missing context variable
would surface here.
"""

from datetime import datetime, timedelta, timezone

from app.jobs.bid_reminders import run_daily_bid_reminders
from app.services.email_service import EmailSendResult


def _deadline_in(days: int) -> str:
    """An ISO deadline `days` days from now (same time-of-day as now)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def make_invitation(
    inv_id: str,
    *,
    deadline: str,
    status: str = "sent",
    pkg_status: str = "open",
    task_name: str = "Rough Grading",
    project_name: str = "Sunrise Meadows",
    contact_name: str = "John Smith",
    contact_email: str = "john@vendor.example",
    company_name: str = "Smith Grading Co.",
    pm_name: str = "Alex Rivera",
    pm_email: str = "alex@bluonx.example",
) -> dict:
    """Build a PostgREST-joined bid_invitations row for FakeReminderDB."""
    return {
        "id": inv_id,
        "vendor_id": f"vendor-{inv_id}",
        "vendor_contact_id": f"contact-{inv_id}",
        "bid_package_id": f"pkg-{inv_id}",
        "status": status,
        "bid_packages": {
            "deadline": deadline,
            "status": pkg_status,
            "created_by": "pm-1",
            "tasks": {"name": task_name, "projects": {"name": project_name}},
            "users": {"full_name": pm_name, "email": pm_email},
        },
        "vendor_contacts": {"full_name": contact_name, "email": contact_email},
        "vendors": {"company_name": company_name},
    }


def make_email_log_row(reference_id: str, *, created_at: str | None = None) -> dict:
    """Build a same-day bid_reminder email_log row for the dedup query."""
    return {
        "email_type": "bid_reminder",
        "reference_type": "bid_invitations",
        "reference_id": reference_id,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }


_COUNTERS = (
    "t_minus_7_sent",
    "t_minus_3_sent",
    "t_minus_0_sent",
    "failed",
    "skipped_already_sent",
    "skipped_status_changed",
)


async def test_no_invitations_due_today_returns_zeros(make_reminder_db, mock_email_service):
    """Empty matching set → job runs cleanly, every counter zero."""
    db = make_reminder_db(invitation_rows=[])

    result = await run_daily_bid_reminders(db, mock_email_service)

    for key in _COUNTERS:
        assert result[key] == 0, key
    assert "duration_seconds" in result
    assert result["duration_seconds"] >= 0
    mock_email_service.send_email.assert_not_awaited()


async def test_t_minus_7_invitation_sends_friendly(make_reminder_db, mock_email_service):
    """Deadline 7 days out → one friendly reminder, t_minus_7_sent=1."""
    db = make_reminder_db(
        invitation_rows=[make_invitation("inv-7", deadline=_deadline_in(7))]
    )

    result = await run_daily_bid_reminders(db, mock_email_service)

    assert result["t_minus_7_sent"] == 1
    assert result["t_minus_3_sent"] == 0
    assert result["t_minus_0_sent"] == 0
    assert result["failed"] == 0

    mock_email_service.send_email.assert_awaited_once()
    kwargs = mock_email_service.send_email.await_args.kwargs
    assert kwargs["email_type"] == "bid_reminder"
    assert kwargs["recipient_type"] == "vendor_contact"
    assert kwargs["reference_type"] == "bid_invitations"
    assert kwargs["reference_id"] == "inv-7"
    assert kwargs["subject"].startswith("Reminder: Bid due in 7 days")
    assert "friendly reminder" in kwargs["html_body"].lower()
    assert "friendly reminder" in kwargs["plain_text_body"].lower()


async def test_t_minus_3_invitation_sends_urgent(make_reminder_db, mock_email_service):
    """Deadline 3 days out → one urgent reminder, t_minus_3_sent=1."""
    db = make_reminder_db(
        invitation_rows=[make_invitation("inv-3", deadline=_deadline_in(3))]
    )

    result = await run_daily_bid_reminders(db, mock_email_service)

    assert result["t_minus_3_sent"] == 1
    assert result["t_minus_7_sent"] == 0
    assert result["t_minus_0_sent"] == 0

    mock_email_service.send_email.assert_awaited_once()
    kwargs = mock_email_service.send_email.await_args.kwargs
    assert kwargs["email_type"] == "bid_reminder"
    assert kwargs["reference_id"] == "inv-3"
    assert kwargs["subject"].startswith("Urgent: Bid due in 3 days")
    assert "approaching quickly" in kwargs["html_body"].lower()
    assert "approaching quickly" in kwargs["plain_text_body"].lower()


async def test_t_minus_0_invitation_sends_final(make_reminder_db, mock_email_service):
    """Deadline today → one final reminder, t_minus_0_sent=1."""
    db = make_reminder_db(
        invitation_rows=[make_invitation("inv-0", deadline=_deadline_in(0))]
    )

    result = await run_daily_bid_reminders(db, mock_email_service)

    assert result["t_minus_0_sent"] == 1
    assert result["t_minus_7_sent"] == 0
    assert result["t_minus_3_sent"] == 0

    mock_email_service.send_email.assert_awaited_once()
    kwargs = mock_email_service.send_email.await_args.kwargs
    assert kwargs["email_type"] == "bid_reminder"
    assert kwargs["reference_id"] == "inv-0"
    assert kwargs["subject"].startswith("Final Call: Bid due today")
    assert "last day" in kwargs["html_body"].lower()
    assert "last day" in kwargs["plain_text_body"].lower()


async def test_mixed_tiers_in_one_run(make_reminder_db, mock_email_service):
    """Three invitations across all tiers → one send each, counts per tier."""
    db = make_reminder_db(
        invitation_rows=[
            make_invitation("inv-7", deadline=_deadline_in(7)),
            make_invitation("inv-3", deadline=_deadline_in(3)),
            make_invitation("inv-0", deadline=_deadline_in(0)),
        ]
    )

    result = await run_daily_bid_reminders(db, mock_email_service)

    assert result["t_minus_7_sent"] == 1
    assert result["t_minus_3_sent"] == 1
    assert result["t_minus_0_sent"] == 1
    assert result["failed"] == 0
    assert mock_email_service.send_email.await_count == 3


async def test_already_sent_today_is_skipped(make_reminder_db, mock_email_service):
    """A same-day bid_reminder email_log row → skip, no send."""
    db = make_reminder_db(
        invitation_rows=[make_invitation("inv-7", deadline=_deadline_in(7))],
        email_log_rows=[make_email_log_row("inv-7")],
    )

    result = await run_daily_bid_reminders(db, mock_email_service)

    assert result["skipped_already_sent"] == 1
    assert result["t_minus_7_sent"] == 0
    mock_email_service.send_email.assert_not_awaited()


async def test_status_changed_to_submitted_between_query_and_send(
    make_reminder_db, mock_email_service
):
    """Fresh status re-read shows 'submitted' → skip, no send."""
    db = make_reminder_db(
        invitation_rows=[make_invitation("inv-7", deadline=_deadline_in(7))],
        status_overrides={"inv-7": "submitted"},
    )

    result = await run_daily_bid_reminders(db, mock_email_service)

    assert result["skipped_status_changed"] == 1
    assert result["t_minus_7_sent"] == 0
    mock_email_service.send_email.assert_not_awaited()


async def test_send_failure_counted_but_job_continues(
    make_reminder_db, mock_email_service
):
    """First send fails → failed=1, second invitation still processed."""
    db = make_reminder_db(
        invitation_rows=[
            make_invitation("inv-a", deadline=_deadline_in(7)),
            make_invitation("inv-b", deadline=_deadline_in(7)),
        ]
    )

    def _send(**kwargs):
        if kwargs["reference_id"] == "inv-a":
            return EmailSendResult(message_id="m", status="failed", error="ses boom")
        return EmailSendResult(message_id="m", status="sent", error=None)

    mock_email_service.send_email.side_effect = _send

    result = await run_daily_bid_reminders(db, mock_email_service)

    assert result["failed"] == 1
    assert result["t_minus_7_sent"] == 1
    assert mock_email_service.send_email.await_count == 2


async def test_excluded_statuses_not_in_query(make_reminder_db, mock_email_service):
    """Invitations in a terminal status are filtered out by the query."""
    rows = [
        make_invitation(f"inv-{st}", deadline=_deadline_in(7), status=st)
        for st in ("submitted", "declined", "expired", "no_response")
    ]
    db = make_reminder_db(invitation_rows=rows)

    result = await run_daily_bid_reminders(db, mock_email_service)

    for key in _COUNTERS:
        assert result[key] == 0, key
    mock_email_service.send_email.assert_not_awaited()


async def test_closed_package_excluded(make_reminder_db, mock_email_service):
    """An invitation under a non-open bid package is excluded by the query."""
    db = make_reminder_db(
        invitation_rows=[
            make_invitation(
                "inv-7", deadline=_deadline_in(7), status="sent", pkg_status="closed"
            )
        ]
    )

    result = await run_daily_bid_reminders(db, mock_email_service)

    assert result["t_minus_7_sent"] == 0
    mock_email_service.send_email.assert_not_awaited()
