"""F.1 — bid_revision_request.{html,txt} render correctly.

Renders the REAL template_renderer singleton (not a mock) so a missing
variable or template typo fails loudly here, before the wiring tests.
"""

from __future__ import annotations

import re

from app.services.template_renderer import template_renderer

_PLACEHOLDER = re.compile(r"\{\{.*?\}\}")

CTX = {
    "vendor_contact_name": "Marcus Delgado",
    "vendor_company_name": "Summit Earthworks LLC",
    "project_name": "Phoenix Logistics Park — Building C",
    "task_name": "Site Grading & Earthwork",
    "pm_note": "Line 1 of the note.\nLine 2 after a blank line.\n\nFinal line.",
    "revision_deadline_formatted": "June 01, 2026 at 05:00 PM UTC",
    "portal_url": "http://localhost:5173/bid/raw-token-abc123",
}


def test_html_contains_all_key_variables():
    html = template_renderer.render("bid_revision_request.html", CTX)
    assert "Marcus Delgado" in html
    assert "Line 1 of the note." in html
    assert "Final line." in html
    assert "June 01, 2026 at 05:00 PM UTC" in html
    assert "http://localhost:5173/bid/raw-token-abc123" in html
    assert "Phoenix Logistics Park — Building C" in html
    # HTML env autoescapes — '&' becomes '&amp;'.
    assert "Site Grading &amp; Earthwork" in html
    # One CTA only — no decline link.
    assert "decline" not in html.lower()


def test_html_has_no_unsubstituted_placeholders():
    html = template_renderer.render("bid_revision_request.html", CTX)
    assert not _PLACEHOLDER.search(html), _PLACEHOLDER.search(html)


def test_txt_partner_contains_key_variables():
    txt = template_renderer.render_text("bid_revision_request.txt", CTX)
    assert "Marcus Delgado" in txt
    assert "Line 1 of the note." in txt
    assert "June 01, 2026 at 05:00 PM UTC" in txt
    assert "http://localhost:5173/bid/raw-token-abc123" in txt
    assert not _PLACEHOLDER.search(txt)
