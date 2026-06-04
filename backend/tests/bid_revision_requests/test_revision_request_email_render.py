"""Task 8.1.5 — `send_revision_request_email` puts desired_start_date in
the render context.

The template's {% if desired_start_date %} block silently falls through
when the key is missing or empty, so a unit test on the sender is the
only way to lock the wiring.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.bid_revision_service import send_revision_request_email
from app.services.email_service import EmailSendResult


def _build_db(*, desired_start_date) -> MagicMock:
    """One-shot Supabase mock returning the joined invitation row."""
    db = MagicMock()
    chain = MagicMock()
    result = MagicMock()
    result.data = {
        "id": str(uuid4()),
        "vendor_contacts": {"full_name": "Jane Doe", "email": "jane@a.example"},
        "vendors": {"company_name": "Apex"},
        "bid_packages": {
            "desired_start_date": desired_start_date,
            "tasks": {
                "name": "Mass Grading",
                "projects": {"name": "North Yard"},
            },
        },
    }
    for m in ("select", "eq", "single"):
        getattr(chain, m).return_value = chain
    chain.execute.return_value = result
    db.table.return_value = chain
    return db


def _make_renderer():
    renderer = MagicMock()
    renderer.render.return_value = "<html></html>"
    renderer.render_text.return_value = "plain"
    return renderer


def _make_email_service():
    svc = AsyncMock()
    svc.send_email.return_value = EmailSendResult(
        message_id="mock-1", status="sent", error=None
    )
    return svc


@pytest.mark.asyncio
async def test_render_context_includes_desired_start_date_when_present():
    db = _build_db(desired_start_date="2026-09-15")
    renderer = _make_renderer()
    svc = _make_email_service()

    sent = await send_revision_request_email(
        email_service=svc,
        template_renderer=renderer,
        db=db,
        bid_invitation_id=uuid4(),
        revision_request_id=uuid4(),
        pm_note="Please re-price line 3.",
        revision_deadline=datetime(2026, 9, 1, 17, 0, tzinfo=timezone.utc),
        portal_url="http://localhost:5173/bid/raw-token",
    )

    assert sent is True
    # Both HTML and text render with the same ctx — check either.
    ctx = renderer.render.call_args.args[1]
    # Renderer is called positionally: render("bid_revision_request.html", ctx)
    assert renderer.render.call_args.args[0] == "bid_revision_request.html"
    assert ctx["desired_start_date"]  # truthy → template will render the row
    assert "September 15, 2026" in ctx["desired_start_date"]


@pytest.mark.asyncio
async def test_render_context_omits_desired_start_date_when_null():
    db = _build_db(desired_start_date=None)
    renderer = _make_renderer()
    svc = _make_email_service()

    await send_revision_request_email(
        email_service=svc,
        template_renderer=renderer,
        db=db,
        bid_invitation_id=uuid4(),
        revision_request_id=uuid4(),
        pm_note="Note.",
        revision_deadline=datetime(2026, 9, 1, 17, 0, tzinfo=timezone.utc),
        portal_url="http://localhost:5173/bid/raw-token",
    )

    ctx = renderer.render.call_args.args[1]
    # Falsy → Jinja's {% if desired_start_date %} omits the row.
    assert not ctx.get("desired_start_date")
