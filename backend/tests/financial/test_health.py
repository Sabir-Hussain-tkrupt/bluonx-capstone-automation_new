"""Contingency health (Phase 5): the pure calculation, the emails and the sweep."""

from __future__ import annotations

from decimal import Decimal as D
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.jobs import financial_health_sweep as sweep
from app.models.contingency import ContingencySettingsUpdate
from app.services import financial_health as fh
from app.services.notification_service import build_notification_deep_link
from app.services.template_renderer import template_renderer


def _input(**over) -> fh.HealthInput:
    base = dict(
        total_budget=D("100000"), contingency=D("5000"), contingency_base=D("10000"),
        lines=(fh.Line(approved=D("30000")),),
    )
    return fh.HealthInput(**{**base, **over})


def _active(data: fh.HealthInput) -> set[str]:
    return {c.type for c in fh.calculate(data).checks if c.active}


def test_discovery_example_alerts():
    r = fh.calculate(_input())
    assert fh.pct_out(r.contingency_left_pct) == "50.00"
    assert fh.pct_out(r.work_left_pct) == "70.00"
    assert _active(_input()) == {fh.HEALTH}


def test_no_buffer_and_exact_boundary():
    # 70% left against 70% work left: equal is not a shortfall.
    assert _active(_input(contingency=D("7000"))) == set()
    assert _active(_input(contingency=D("6999.99"))) == {fh.HEALTH}


def test_uses_whichever_shows_more_work_left():
    r = fh.calculate(_input(milestones_total=10, milestones_completed=1))
    assert (r.work_left_basis, fh.pct_out(r.work_left_pct)) == ("physical", "90.00")
    r = fh.calculate(_input(milestones_total=10, milestones_completed=9))
    assert (r.work_left_basis, fh.pct_out(r.work_left_pct)) == ("dollars", "70.00")


def test_committed_then_paid_counts_once():
    r = fh.calculate(_input(lines=(
        fh.Line(committed=D("20000"), approved=D("5000"), sent=D("3000")),
        fh.Line(approved=D("1000")),
        fh.Line(land_closed=D("4000")),
    )))
    assert (r.committed, r.approved, r.sent, r.land_closed) == (D("12000"), D("6000"), D("3000"), D("4000"))
    assert r.spent == D("25000")


@pytest.mark.parametrize(("amount", "expected"), [
    ("501", set()), ("500", {fh.NEAR_ZERO}), ("0", {fh.NEAR_ZERO}), ("-0.01", {fh.NEGATIVE}),
])
def test_near_zero_and_negative(amount, expected):
    assert _active(_input(contingency=D(amount))) - {fh.HEALTH} == expected


def test_reserve_alerts_even_when_healthy():
    data = _input(contingency=D("9000"), reserve=D("9500"))
    assert _active(data) == {fh.RESERVE}
    assert _active(_input(contingency=D("9500"), reserve=D("9500"))) == set()


def test_closed_project_has_no_active_checks():
    assert _active(_input(contingency=D("-1"), reserve=D("500"), live=False)) == set()


def test_no_denominator_is_not_an_alert():
    assert _active(_input(contingency_base=D("0"), contingency=D("0"))) == set()
    assert _active(_input(contingency_base=None, total_budget=D("0"))) == set()


def test_from_row_is_live_only_for_open_baselined_projects():
    row = {"budget_status": "baselined", "status": "active", "archived": False, "contingency": 5000,
           "contingency_base": 10000, "total_budget": 100000, "lines": [], "near_zero_percent": 5}
    assert fh.from_row(row).live
    for over in ({"budget_status": "draft"}, {"status": "completed"}, {"archived": True}):
        assert not fh.from_row({**row, **over}).live


@pytest.mark.parametrize("name", [
    "contingency_health_alert", "contingency_urgent_alert", "long_tail_reserve_alert",
    "contingency_executive_escalation",
])
def test_emails_render(name):
    ctx = {"project_name": "<Oak>", "message": "Low contingency", "contingency": "$5,000.00", "left_pct": "50.00",
           "work_left_pct": None, "reserve": None, "link": "https://app.test/financial-alerts/1", "why": "Because"}
    html = template_renderer.render(f"{name}.html", ctx)
    text = template_renderer.render_text(f"{name}.txt", ctx)
    for body in (html, text):
        assert "Low contingency" in body and "https://app.test/financial-alerts/1" in body and "None" not in body
        assert "Work left" not in body
    assert "&lt;Oak&gt;" in html


def test_notification_opens_the_decision_screen():
    n = {"reference_type": "financial_alerts", "reference_id": "a1"}
    assert build_notification_deep_link(n, MagicMock()) == "/financial-alerts/a1"


def test_recipient_settings_are_cleaned():
    s = ContingencySettingsUpdate(alert_recipients={"urgent": [" a@x.com ", "A@x.com", ""]})
    assert s.model_dump(exclude_none=True)["alert_recipients"] == {"warning": [], "urgent": ["a@x.com"], "critical": []}


async def test_sweep_isolates_a_failing_project(monkeypatch):
    def recalc(_db, project_id):
        if project_id == "bad":
            raise RuntimeError("boom")
        return ["new"]

    monkeypatch.setattr(sweep, "_project_ids", lambda _db: ["ok", "bad"])
    monkeypatch.setattr(sweep.svc, "recalculate", recalc)
    monkeypatch.setattr(sweep.notify, "sweep_project", AsyncMock(return_value={"sent": 1, "escalated": 0}))
    out = await sweep.run_financial_health_sweep(MagicMock(), MagicMock())
    assert (out["projects"], out["opened"], out["sent"], out["failed"]) == (1, 1, 1, 1)
