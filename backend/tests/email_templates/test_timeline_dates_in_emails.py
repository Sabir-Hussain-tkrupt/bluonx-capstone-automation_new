"""Task 8.1.5 — desired/proposed start dates render in the right email
templates and are conditionally shown.

Renders the REAL template_renderer (matching the pattern used by
backend/tests/email_templates/test_bid_revision_request_email.py).
"""

from __future__ import annotations

from app.services.template_renderer import template_renderer


# ── Common variables every template expects ──────────────────────────────

_COMMON = {
    "vendor_contact_name": "Marcus Delgado",
    "vendor_company_name": "Summit Earthworks",
    "project_name": "Phoenix Logistics Park",
    "project_location": "Phoenix, AZ",
    "project_description": "Phase 1 site work.",
    "task_name": "Mass Grading",
    "task_description": "Bring pads to subgrade.",
    "bid_deadline": "June 01, 2026 at 05:00 PM UTC",
    "deadline": "June 01, 2026 at 05:00 PM UTC",
    "bid_format": "Lump Sum",
    "document_names": [],
    "magic_link_url": "http://localhost:5173/bid/token-abc",
    "pm_name": "Alex Rivera",
    "pm_email": "alex@bluonx.dev",
}


# ── bid_invitation (initial invite) ──────────────────────────────────────


def test_bid_invitation_html_shows_desired_start_date_when_present():
    ctx = {**_COMMON, "desired_start_date": "September 15, 2026"}
    html = template_renderer.render("bid_invitation.html", ctx)
    assert "September 15, 2026" in html
    # The row label should be present so the date is parseable in the UI.
    assert "Desired Start" in html or "Desired start" in html


def test_bid_invitation_html_omits_desired_row_when_absent():
    ctx = {**_COMMON, "desired_start_date": None}
    html = template_renderer.render("bid_invitation.html", ctx)
    assert "Desired Start" not in html and "Desired start" not in html


def test_bid_invitation_txt_shows_desired_start_date_when_present():
    ctx = {**_COMMON, "desired_start_date": "September 15, 2026"}
    txt = template_renderer.render_text("bid_invitation.txt", ctx)
    assert "September 15, 2026" in txt


def test_bid_invitation_txt_omits_desired_when_absent():
    ctx = {**_COMMON, "desired_start_date": None}
    txt = template_renderer.render_text("bid_invitation.txt", ctx)
    assert "Desired Start" not in txt and "Desired start" not in txt


# ── bid_revision_request (PM-initiated revision) ─────────────────────────

_REVISION_COMMON = {
    "vendor_contact_name": "Marcus Delgado",
    "vendor_company_name": "Summit Earthworks",
    "project_name": "Phoenix Logistics Park",
    "task_name": "Mass Grading",
    "pm_note": "Please re-price.",
    "revision_deadline_formatted": "June 01, 2026 at 05:00 PM UTC",
    "portal_url": "http://localhost:5173/bid/raw-token",
}


def test_revision_request_html_shows_desired_start_date_when_present():
    ctx = {**_REVISION_COMMON, "desired_start_date": "September 15, 2026"}
    html = template_renderer.render("bid_revision_request.html", ctx)
    assert "September 15, 2026" in html


def test_revision_request_html_omits_desired_when_absent():
    ctx = {**_REVISION_COMMON, "desired_start_date": None}
    html = template_renderer.render("bid_revision_request.html", ctx)
    assert "September 15, 2026" not in html


# ── bid_revision_submitted (vendor receipt for a revision) ───────────────

_RECEIPT_COMMON = {
    "vendor_contact_name": "Marcus Delgado",
    "vendor_company_name": "Summit Earthworks",
    "project_name": "Phoenix Logistics Park",
    "task_name": "Mass Grading",
    "submitted_at": "June 01, 2026 at 05:00 PM UTC",
    "total_amount": "47500.00",
    "attachment_count": 0,
    "pm_name": "Alex Rivera",
    "pm_email": "alex@bluonx.dev",
}


def test_revision_submitted_html_shows_proposed_start_date_when_present():
    ctx = {**_RECEIPT_COMMON, "proposed_start_date": "September 20, 2026"}
    html = template_renderer.render("bid_revision_submitted.html", ctx)
    assert "September 20, 2026" in html
    assert "Proposed Start" in html or "Proposed start" in html


def test_revision_submitted_html_omits_proposed_when_absent():
    ctx = {**_RECEIPT_COMMON, "proposed_start_date": None}
    html = template_renderer.render("bid_revision_submitted.html", ctx)
    assert "Proposed Start" not in html and "Proposed start" not in html
