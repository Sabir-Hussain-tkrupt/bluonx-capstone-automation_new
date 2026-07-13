"""Phase 10.4: milestone emails, send helpers, and notifications.

Covers:
  * every template renders (full ctx AND optional fields absent), .txt partner too
  * scanner-safety: vendor emails carry ONE portal link and zero answer-bearing links
  * subjects built correctly per check / alert type
  * PM emails carry the vendor contact block + the "paused until you act" stall copy
  * send helpers never raise, return False with no deliverable email, and pass the
    correct email_type / recipient_type / reference_type / reference_id
  * build_notification_deep_link resolves the milestone route
  * create_notification gates the milestone vocabulary; notify_* wrappers dispatch correctly
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.email_service import EmailSendResult
from app.services.milestone_email_service import (
    send_milestone_check_email,
    send_milestone_pm_alert_email,
)
from app.services.template_renderer import template_renderer

_PLACEHOLDER = re.compile(r"\{\{.*?\}\}")
_HREF = re.compile(r'href="([^"]*)"')

VENDOR_STEMS = (
    "milestone_start_check",
    "milestone_progress_check",
    "milestone_completion_check",
)
PM_STEMS = ("milestone_delay_alert", "milestone_no_response_alert")

_PORTAL_URL = "http://localhost:5173/milestone/raw-token-abc123"
_MILESTONE_URL = "http://localhost:5173/projects/p1/tasks/t1/milestones/m1"

_VENDOR_CTX = {
    "vendor_contact_name": "Marcus Delgado",
    "company_name": "Summit Earthworks LLC",
    "project_name": "Phoenix Logistics Park - Building C",
    "task_name": "Site Grading & Earthwork",
    "milestone_name": "Rough Grading Complete",
    "start_date_formatted": "September 15, 2026",
    "end_date_formatted": "October 03, 2026",
    "portal_url": _PORTAL_URL,
}

_PM_CTX = {
    "recipient_full_name": "Dana Whitfield",
    "project_name": "Phoenix Logistics Park - Building C",
    "task_name": "Site Grading & Earthwork",
    "milestone_name": "Rough Grading Complete",
    "vendor_company_name": "Summit Earthworks LLC",
    "vendor_contact_name": "Marcus Delgado",
    "vendor_contact_email": "marcus@summit.example",
    "vendor_contact_phone": "(602) 555-0148",
    "end_date_formatted": "October 03, 2026",
    "milestone_url": _MILESTONE_URL,
    "check_type_label": "start confirmation",
    "days_silent": 4,
}


# ── Template rendering ────────────────────────────────────────────────────


@pytest.mark.parametrize("stem", VENDOR_STEMS)
def test_vendor_template_renders_full_and_txt_partner(stem):
    html = template_renderer.render(f"{stem}.html", _VENDOR_CTX)
    txt = template_renderer.render_text(f"{stem}.txt", _VENDOR_CTX)
    assert "Marcus Delgado" in html
    assert "Rough Grading Complete" in html
    assert _PORTAL_URL in html
    assert not _PLACEHOLDER.search(html)
    assert _PORTAL_URL in txt
    assert not _PLACEHOLDER.search(txt)


@pytest.mark.parametrize("stem", VENDOR_STEMS)
def test_vendor_template_renders_with_optional_dates_absent(stem):
    ctx = {k: v for k, v in _VENDOR_CTX.items()
           if k not in ("start_date_formatted", "end_date_formatted")}
    html = template_renderer.render(f"{stem}.html", ctx)
    txt = template_renderer.render_text(f"{stem}.txt", ctx)
    assert not _PLACEHOLDER.search(html)
    assert not _PLACEHOLDER.search(txt)


@pytest.mark.parametrize("stem", PM_STEMS)
def test_pm_template_renders_full_and_txt_partner(stem):
    html = template_renderer.render(f"{stem}.html", _PM_CTX)
    txt = template_renderer.render_text(f"{stem}.txt", _PM_CTX)
    # Vendor contact block present so the PM can call without hunting.
    for value in ("Summit Earthworks LLC", "marcus@summit.example", "(602) 555-0148"):
        assert value in html
        assert value in txt
    # The stall is the whole reason for the email; state it plainly.
    assert "paused until you act" in html
    assert "PAUSED until you act" in txt
    assert _MILESTONE_URL in html
    assert not _PLACEHOLDER.search(html)
    assert not _PLACEHOLDER.search(txt)


@pytest.mark.parametrize("stem", PM_STEMS)
def test_pm_template_renders_with_optional_fields_absent(stem):
    ctx = {k: v for k, v in _PM_CTX.items()
           if k not in ("vendor_contact_phone", "check_type_label", "days_silent",
                        "end_date_formatted")}
    html = template_renderer.render(f"{stem}.html", ctx)
    txt = template_renderer.render_text(f"{stem}.txt", ctx)
    assert not _PLACEHOLDER.search(html)
    assert not _PLACEHOLDER.search(txt)


# ── Scanner-safety guarantee ──────────────────────────────────────────────


@pytest.mark.parametrize("stem", VENDOR_STEMS)
def test_vendor_email_has_single_portal_link_and_no_answer_links(stem):
    html = template_renderer.render(f"{stem}.html", _VENDOR_CTX)
    txt = template_renderer.render_text(f"{stem}.txt", _VENDOR_CTX)

    # Every href in a vendor email points at the portal magic link, nothing else.
    hrefs = set(_HREF.findall(html))
    assert hrefs == {_PORTAL_URL}, f"unexpected hrefs in {stem}: {hrefs}"

    # No answer-bearing link can appear anywhere: a scanner pre-fetching links
    # must never be able to respond on the vendor's behalf.
    for body in (html.lower(), txt.lower()):
        assert "response=yes" not in body
        assert "response=no" not in body
        assert "?response" not in body


# ── Fake Supabase client ──────────────────────────────────────────────────


class _Query:
    """Chainable no-op query whose execute() returns a preset result."""

    def __init__(self, result):
        self._result = result

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        return self._result


class _DB:
    def __init__(self, per_table):
        self._per_table = per_table

    def table(self, name):
        return _Query(self._per_table[name])


def _milestone_row():
    return SimpleNamespace(data={
        "id": "m1",
        "name": "Rough Grading Complete",
        "start_date": "2026-09-15",
        "end_date": "2026-10-03",
        "task_id": "t1",
        "contract_id": "c1",
        "tasks": {"name": "Site Grading", "project_id": "p1",
                  "projects": {"name": "North Yard"}},
        "contracts": {"vendor_id": "v1", "vendors": {"company_name": "Summit"}},
    })


def _contact_rows(email="marcus@summit.example"):
    return SimpleNamespace(data=[{"full_name": "Marcus", "email": email, "phone": "555"}])


def _email_service():
    svc = AsyncMock()
    svc.send_email.return_value = EmailSendResult(message_id="x", status="sent", error=None)
    return svc


# ── Send helper: vendor check-in ──────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "check_type,expected_subject",
    [
        ("start", "Quick check-in: Rough Grading Complete at North Yard"),
        ("progress", "On track? Rough Grading Complete at North Yard"),
        ("completion", "Is Rough Grading Complete complete?"),
    ],
)
async def test_check_email_sends_with_correct_metadata(check_type, expected_subject):
    db = _DB({"milestones": _milestone_row(), "vendor_contacts": _contact_rows()})
    svc = _email_service()

    ok = await send_milestone_check_email(
        milestone_id="m1", check_type=check_type, portal_url=_PORTAL_URL,
        db=db, email_service=svc,
    )

    assert ok is True
    kwargs = svc.send_email.await_args.kwargs
    assert kwargs["subject"] == expected_subject
    assert kwargs["email_type"] == "milestone_alert"
    assert kwargs["recipient_type"] == "vendor_contact"
    assert kwargs["reference_type"] == "milestones"
    assert kwargs["reference_id"] == "m1"
    assert kwargs["to_email"] == "marcus@summit.example"


@pytest.mark.asyncio
async def test_check_email_returns_false_when_no_contact_email():
    db = _DB({"milestones": _milestone_row(), "vendor_contacts": _contact_rows(email="")})
    svc = _email_service()

    ok = await send_milestone_check_email(
        milestone_id="m1", check_type="start", portal_url=_PORTAL_URL,
        db=db, email_service=svc,
    )

    assert ok is False
    svc.send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_email_never_raises_on_unreadable_milestone():
    db = _DB({"milestones": SimpleNamespace(data={}), "vendor_contacts": _contact_rows()})
    svc = _email_service()

    ok = await send_milestone_check_email(
        milestone_id="m1", check_type="start", portal_url=_PORTAL_URL,
        db=db, email_service=svc,
    )
    # Empty milestone → no vendor_id → no deliverable email → False, not an exception.
    assert ok is False


# ── Send helper: PM alert ─────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alert_type,expected_subject",
    [
        ("delay", "Delay reported: Rough Grading Complete at North Yard"),
        ("no_response", "No response: Rough Grading Complete at North Yard"),
    ],
)
async def test_pm_alert_sends_with_correct_metadata(alert_type, expected_subject):
    db = _DB({
        "milestones": _milestone_row(),
        "vendor_contacts": _contact_rows(),
        "users": SimpleNamespace(data={"full_name": "Dana", "email": "dana@pm.example"}),
    })
    svc = _email_service()

    ok = await send_milestone_pm_alert_email(
        milestone_id="m1", alert_type=alert_type, recipient_user_id="u1",
        db=db, email_service=svc, check_type_label="start confirmation", days_silent=4,
    )

    assert ok is True
    kwargs = svc.send_email.await_args.kwargs
    assert kwargs["subject"] == expected_subject
    assert kwargs["email_type"] == "milestone_alert"
    assert kwargs["recipient_type"] == "user"
    assert kwargs["reference_type"] == "milestones"
    assert kwargs["reference_id"] == "m1"
    assert kwargs["to_email"] == "dana@pm.example"


@pytest.mark.asyncio
async def test_pm_alert_returns_false_when_recipient_has_no_email():
    db = _DB({
        "milestones": _milestone_row(),
        "vendor_contacts": _contact_rows(),
        "users": SimpleNamespace(data={"full_name": "Dana", "email": ""}),
    })
    svc = _email_service()

    ok = await send_milestone_pm_alert_email(
        milestone_id="m1", alert_type="delay", recipient_user_id="u1",
        db=db, email_service=svc,
    )

    assert ok is False
    svc.send_email.assert_not_awaited()


# ── Notifications: vocabulary + deep link ─────────────────────────────────


def test_create_notification_rejects_unknown_milestone_type():
    from app.services.notification_service import create_notification

    with pytest.raises(ValueError):
        create_notification(
            MagicMock(), user_id=uuid4(), notification_type="milestone_bogus",
            title="x",
        )


@pytest.mark.parametrize(
    "ntype",
    ["milestone_delayed", "milestone_unresponsive", "milestone_completed"],
)
def test_create_notification_accepts_new_milestone_types(ntype):
    from app.services.notification_service import NOTIFICATION_TYPES

    assert ntype in NOTIFICATION_TYPES


def test_build_deep_link_resolves_milestone_route():
    from app.services.notification_service import build_notification_deep_link

    db = _DB({"milestones": SimpleNamespace(
        data=[{"id": "m1", "task_id": "t1", "tasks": {"project_id": "p1"}}]
    )})
    path = build_notification_deep_link(
        {"reference_type": "milestones", "reference_id": "m1"}, db
    )
    assert path == "/projects/p1/tasks/t1/milestones/m1"


# ── Notification helpers ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "func_name,expected_type,expected_title",
    [
        ("notify_milestone_delayed", "milestone_delayed", "Delay reported: Rough Grading Complete"),
        ("notify_milestone_unresponsive", "milestone_unresponsive", "No response: Rough Grading Complete"),
        ("notify_milestone_completed", "milestone_completed", "Completed: Rough Grading Complete"),
    ],
)
def test_notify_helpers_dispatch_to_created_by(monkeypatch, func_name,
                                               expected_type, expected_title):
    import app.services.milestone_notification_service as mod

    captured = {}

    def _fake_create(db, **kwargs):
        captured.update(kwargs)
        return {"id": "n1", **kwargs}

    monkeypatch.setattr(mod, "create_notification", _fake_create)

    db = _DB({"milestones": SimpleNamespace(
        data=[{"id": "m1", "name": "Rough Grading Complete", "created_by": "pm-1"}]
    )})

    result = getattr(mod, func_name)(db, "m1")

    assert result is not None
    assert captured["user_id"] == "pm-1"
    assert captured["notification_type"] == expected_type
    assert captured["title"] == expected_title
    assert captured["reference_type"] == "milestones"
    assert captured["reference_id"] == "m1"


def test_notify_helper_skips_when_no_created_by(monkeypatch):
    import app.services.milestone_notification_service as mod

    called = MagicMock()
    monkeypatch.setattr(mod, "create_notification", called)

    db = _DB({"milestones": SimpleNamespace(
        data=[{"id": "m1", "name": "X", "created_by": None}]
    )})
    result = mod.notify_milestone_completed(db, "m1")

    assert result is None
    called.assert_not_called()
