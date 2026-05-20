"""F.2 — bid_revision_submitted.{html,txt} render correctly.

Renders the REAL template_renderer singleton so a missing variable or
template typo fails loudly here, before the wiring tests.
"""

from __future__ import annotations

import re

from app.services.template_renderer import template_renderer

_PLACEHOLDER = re.compile(r"\{\{.*?\}\}")

CTX = {
    "vendor_contact_name": "Marcus Delgado",
    "vendor_company_name": "Summit Earthworks LLC",
    "project_name": "Phoenix Logistics Park",
    "task_name": "Site Grading",
    "total_amount_formatted": "$52,800.00",
    "submitted_at_formatted": "June 01, 2026 at 05:00 PM UTC",
    "pm_name": "Dana Ruiz",
    "pm_email": "dana@bluonx.example",
}


def test_html_contains_all_key_variables():
    html = template_renderer.render("bid_revision_submitted.html", CTX)
    assert "Marcus Delgado" in html
    assert "Summit Earthworks LLC" in html
    assert "Phoenix Logistics Park" in html
    assert "Site Grading" in html
    assert "$52,800.00" in html
    assert "June 01, 2026 at 05:00 PM UTC" in html
    assert "Dana Ruiz" in html
    assert "original bid remains preserved" in html.lower()


def test_html_has_no_unsubstituted_placeholders():
    html = template_renderer.render("bid_revision_submitted.html", CTX)
    assert not _PLACEHOLDER.search(html), _PLACEHOLDER.search(html)


def test_pm_block_omitted_when_pm_absent():
    ctx = {**CTX, "pm_name": None, "pm_email": None}
    html = template_renderer.render("bid_revision_submitted.html", ctx)
    assert "Dana Ruiz" not in html
    assert not _PLACEHOLDER.search(html)


def test_txt_partner_contains_key_variables():
    txt = template_renderer.render_text("bid_revision_submitted.txt", CTX)
    assert "Marcus Delgado" in txt
    assert "Phoenix Logistics Park" in txt
    assert "Site Grading" in txt
    assert "$52,800.00" in txt
    assert "June 01, 2026 at 05:00 PM UTC" in txt
    assert not _PLACEHOLDER.search(txt)
