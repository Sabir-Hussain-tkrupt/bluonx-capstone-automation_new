"""Long-tail items (Phase 7): reminder tiers, schemas and emails."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.jobs.long_tail_reminders import bond_tier, tax_tier
from app.models.long_tail import EscrowSave, TaxYearSave
from app.services.notification_service import build_notification_deep_link
from app.services.template_renderer import template_renderer


@pytest.mark.parametrize(("days", "reminded", "expected"), [
    (31, None, None), (30, None, 30), (20, 30, None), (7, 30, 7), (7, None, 7), (3, 7, None), (-1, None, None),
])
def test_tax_reminder_tiers(days, reminded, expected):
    assert tax_tier(days, 30, reminded) == expected


@pytest.mark.parametrize(("days", "sent", "expected"), [
    (61, set(), None), (60, set(), 60), (40, {60}, None), (14, {60}, 14), (10, set(), 14), (5, {14}, None),
    (-3, {60}, 14),
])
def test_bond_reminder_tiers(days, sent, expected):
    assert bond_tier(days, 60, sent) == expected


def test_escrow_needs_an_area():
    base = {"name": "Roads", "beneficiary": "city", "security_form": "bond", "secured_amount": "10000"}
    with pytest.raises(ValidationError):
        EscrowSave(**base, covered_areas=["  "])
    e = EscrowSave(**base, covered_areas=[" landscaping ", "trails", "benches"])
    assert e.covered_areas == ["landscaping", "trails", "benches"]


def test_tax_year_basis_needs_its_inputs():
    j = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(ValidationError):
        TaxYearSave(tax_year=2027, jurisdiction_id=j, estimate_basis="manual")
    with pytest.raises(ValidationError):
        TaxYearSave(tax_year=2027, jurisdiction_id=j, estimate_basis="assessed_value", assessed_value=Decimal("1"))
    assert TaxYearSave(tax_year=2028, jurisdiction_id=j, estimate_basis="prior_year_actual").amount is None


@pytest.mark.parametrize("name", ["property_tax_reminder", "bond_renewal_reminder"])
def test_reminder_emails_render(name):
    ctx = {"heading": "Due soon", "intro": "Pay it", "rows": [("Project", "Oak")], "link": "https://x.test/l"}
    assert "Oak" in template_renderer.render(f"{name}.html", ctx)
    assert "https://x.test/l" in template_renderer.render_text(f"{name}.txt", ctx)


def test_reminders_open_the_long_tail_tab():
    n = {"reference_type": "long_tail", "reference_id": "p1"}
    assert build_notification_deep_link(n, None) == "/projects/p1?tab=long-tail"
