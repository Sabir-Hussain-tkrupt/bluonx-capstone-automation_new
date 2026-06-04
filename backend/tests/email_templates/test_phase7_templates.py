"""Render tests for Phase 7 email templates (Task 7.2).

Renders the REAL template_renderer singleton so a missing variable or a
template typo fails loudly here, before any send-site wiring (Tasks
7.3/7.4/7.5/7.7). Covers the three new digest/alert templates plus
render-smoke coverage for the three pre-existing bid_reminder tiers.
"""

from __future__ import annotations

import re

import pytest

from app.services.template_renderer import template_renderer

_PLACEHOLDER = re.compile(r"\{\{.*?\}\}")


def _assert_no_placeholders(rendered: str) -> None:
    leftover = _PLACEHOLDER.search(rendered)
    assert leftover is None, f"unsubstituted placeholder: {leftover}"


# ── insurance_expiration_digest ─────────────────────────────────────────────

_INS_7DAY = [
    {
        "company_name": "Summit Earthworks LLC",
        "vendor_contact": "marcus@summit-earth.example",
        "expiration_date_formatted": "May 29, 2026",
    },
]
_INS_30DAY = [
    {
        "company_name": "Ironclad Concrete & Paving",
        "vendor_contact": "lena@ironclad.example",
        "expiration_date_formatted": "June 21, 2026",
    },
    {
        "company_name": "Apex Mechanical Services",
        "vendor_contact": "tara@apexmech.example",
        "expiration_date_formatted": "June 22, 2026",
    },
]


def _insurance_ctx(items_7day, items_30day) -> dict:
    return {
        "admin_full_name": "Dana Whitfield",
        "items_7day": items_7day,
        "items_30day": items_30day,
        "items_total": len(items_7day) + len(items_30day),
    }


def test_insurance_digest_html_both_sections():
    html = template_renderer.render(
        "insurance_expiration_digest.html", _insurance_ctx(_INS_7DAY, _INS_30DAY)
    )
    assert "Dana Whitfield" in html
    assert "Summit Earthworks LLC" in html
    assert "Apex Mechanical Services" in html
    # HTML env autoescapes — '&' becomes '&amp;'.
    assert "Ironclad Concrete &amp; Paving" in html
    assert "marcus@summit-earth.example" in html
    assert "lena@ironclad.example" in html
    assert "Expiring in 7 Days" in html
    assert "Expiring in 30 Days" in html
    assert "May 29, 2026" in html
    assert "June 21, 2026" in html
    _assert_no_placeholders(html)


def test_insurance_digest_txt_both_sections():
    txt = template_renderer.render_text(
        "insurance_expiration_digest.txt", _insurance_ctx(_INS_7DAY, _INS_30DAY)
    )
    assert "Dana Whitfield" in txt
    assert "Summit Earthworks LLC" in txt
    # Text env does not autoescape — '&' stays literal.
    assert "Ironclad Concrete & Paving" in txt
    assert "marcus@summit-earth.example" in txt
    assert "lena@ironclad.example" in txt
    assert "EXPIRING IN 7 DAYS" in txt
    assert "EXPIRING IN 30 DAYS" in txt
    _assert_no_placeholders(txt)


def test_insurance_digest_only_7day_section():
    ctx = _insurance_ctx(_INS_7DAY, [])
    html = template_renderer.render("insurance_expiration_digest.html", ctx)
    txt = template_renderer.render_text("insurance_expiration_digest.txt", ctx)
    assert "Expiring in 7 Days" in html
    assert "Expiring in 30 Days" not in html
    assert "EXPIRING IN 7 DAYS" in txt
    assert "EXPIRING IN 30 DAYS" not in txt
    _assert_no_placeholders(html)
    _assert_no_placeholders(txt)


def test_insurance_digest_only_30day_section():
    ctx = _insurance_ctx([], _INS_30DAY)
    html = template_renderer.render("insurance_expiration_digest.html", ctx)
    txt = template_renderer.render_text("insurance_expiration_digest.txt", ctx)
    assert "Expiring in 30 Days" in html
    assert "Expiring in 7 Days" not in html
    assert "EXPIRING IN 30 DAYS" in txt
    assert "EXPIRING IN 7 DAYS" not in txt
    _assert_no_placeholders(html)
    _assert_no_placeholders(txt)


def test_insurance_digest_empty_renders_cleanly():
    """Both tiers empty — must still render without raising (the caller skips
    the send, but the template must never crash)."""
    ctx = _insurance_ctx([], [])
    html = template_renderer.render("insurance_expiration_digest.html", ctx)
    txt = template_renderer.render_text("insurance_expiration_digest.txt", ctx)
    assert "Dana Whitfield" in html
    assert "Expiring in 7 Days" not in html
    assert "Expiring in 30 Days" not in html
    _assert_no_placeholders(html)
    _assert_no_placeholders(txt)


# ── post_deadline_escalation_digest ─────────────────────────────────────────

_ESCALATION_CTX = {
    "recipient_full_name": "Priya Nair",
    "packages_count": 2,
    "packages": [
        {
            "project_name": "Phoenix Logistics Park — Building C",
            "task_name": "Site Grading & Earthwork",
            "deadline_formatted": "May 21, 2026 at 05:00 PM UTC",
            "non_responders": [
                {
                    "company_name": "Summit Earthworks LLC",
                    "contact_name": "Marcus Delgado",
                    "contact_email": "marcus@summit-earth.example",
                    "contact_phone": "(602) 555-0142",
                },
            ],
        },
        {
            "project_name": "Cedar Ridge Subdivision",
            "task_name": "Storm Drainage",
            "deadline_formatted": "May 21, 2026 at 05:00 PM UTC",
            "non_responders": [
                {
                    "company_name": "Ironclad Concrete & Paving",
                    "contact_name": "Lena Ortiz",
                    "contact_email": "lena@ironclad.example",
                    "contact_phone": "(480) 555-0199",
                },
            ],
        },
    ],
}


def test_escalation_digest_html_renders():
    html = template_renderer.render(
        "post_deadline_escalation_digest.html", _ESCALATION_CTX
    )
    assert "Priya Nair" in html
    assert "Phoenix Logistics Park" in html
    assert "Cedar Ridge Subdivision" in html
    assert "Marcus Delgado" in html
    assert "marcus@summit-earth.example" in html
    assert "(602) 555-0142" in html
    assert "Ironclad Concrete &amp; Paving" in html
    # Recommended actions.
    assert "Contact the vendor directly" in html
    assert "Extend the deadline and issue a new bid invitation" in html
    assert "Award based on submitted bids" in html
    _assert_no_placeholders(html)


def test_escalation_digest_txt_renders():
    txt = template_renderer.render_text(
        "post_deadline_escalation_digest.txt", _ESCALATION_CTX
    )
    assert "Priya Nair" in txt
    assert "Cedar Ridge Subdivision" in txt
    assert "Site Grading & Earthwork" in txt
    assert "Marcus Delgado" in txt
    assert "(480) 555-0199" in txt
    assert "Contact the vendor directly" in txt
    assert "Award based on submitted bids" in txt
    _assert_no_placeholders(txt)


# ── scheduler_self_check_alert ──────────────────────────────────────────────

_SELF_CHECK_CTX = {
    "admin_full_name": "Dana Whitfield",
    "stale_count": 2,
    "stale_jobs": [
        {
            "job_id": "daily_bid_reminders",
            "expected_interval": "daily",
            "last_run_at_formatted": "May 20, 2026 at 08:00 AM UTC",
            "status": "stale",
        },
        {
            "job_id": "revision_expiry",
            "expected_interval": "hourly",
            "last_run_at_formatted": "never",
            "status": "stale",
        },
    ],
}


def test_self_check_alert_html_renders():
    html = template_renderer.render("scheduler_self_check_alert.html", _SELF_CHECK_CTX)
    assert "Dana Whitfield" in html
    assert "daily_bid_reminders" in html
    assert "revision_expiry" in html
    assert "hourly" in html
    assert "May 20, 2026 at 08:00 AM UTC" in html
    assert "/api/v1/admin/scheduler-health" in html
    _assert_no_placeholders(html)


def test_self_check_alert_txt_renders():
    txt = template_renderer.render_text(
        "scheduler_self_check_alert.txt", _SELF_CHECK_CTX
    )
    assert "Dana Whitfield" in txt
    assert "daily_bid_reminders" in txt
    assert "revision_expiry" in txt
    assert "/api/v1/admin/scheduler-health" in txt
    _assert_no_placeholders(txt)


# ── existing bid_reminder tiers (regression smoke) ──────────────────────────

# Reminders intentionally do NOT mint a new magic link (Task 7.3 design):
# they point vendors back to their original invitation email, so the three
# bid_reminder_* templates do not reference `magic_link_url`. Don't add it
# back to the context — keep this in sync with the templates' actual surface.
_REMINDER_CTX = {
    "vendor_contact_name": "Marcus Delgado",
    "task_name": "Site Grading & Earthwork",
    "project_name": "Phoenix Logistics Park — Building C",
    "bid_deadline": "May 29, 2026 at 05:00 PM UTC",
    "pm_name": "Priya Nair",
    "pm_email": "priya@bluonx.example",
    "company_name": "BluOnX Development LLC",
}


@pytest.mark.parametrize("tier", ["friendly", "urgent", "final"])
def test_bid_reminder_tier_renders(tier):
    """Smoke test — guards the verify-pass for the three existing tiers."""
    html = template_renderer.render(f"bid_reminder_{tier}.html", _REMINDER_CTX)
    txt = template_renderer.render_text(f"bid_reminder_{tier}.txt", _REMINDER_CTX)
    for rendered in (html, txt):
        assert "Marcus Delgado" in rendered
        assert "May 29, 2026 at 05:00 PM UTC" in rendered
        assert "Priya Nair" in rendered
        _assert_no_placeholders(rendered)
