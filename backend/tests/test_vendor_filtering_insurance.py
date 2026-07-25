"""
Insurance behaviour of the vendor filtering pipeline — the first coverage of
filter_qualified_vendors.

Focus: the expired-vs-lapses-before-project-end split. Projects here have no
coordinates, so the distance stage is skipped and the tests stay on the
insurance axis (no Routes API involved).
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.services.vendor_filtering import filter_qualified_vendors
from tests._fakes import FakeResponse, FakeSupabase


TODAY = date.today()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()
NEXT_MONTH = (TODAY + timedelta(days=30)).isoformat()
NEXT_YEAR = (TODAY + timedelta(days=365)).isoformat()
LAST_MONTH = (TODAY - timedelta(days=30)).isoformat()

TASK_ID = str(uuid4())
PROJECT_ID = str(uuid4())
TRADE_ID = str(uuid4())


def _vendor(insurance_expiration_date, **overrides):
    """A vendor that passes every check except (possibly) insurance."""
    base = {
        "id": str(uuid4()),
        "company_name": "V",
        "status": "active",
        "onboarding_status": "complete",
        "insurance_expiration_date": insurance_expiration_date,
        "bonding_capacity": None,   # budget None below → bonding skipped
        "max_active_jobs": None,    # → capacity skipped
        "current_active_jobs": 0,
        "latitude": None,
        "longitude": None,
    }
    base.update(overrides)
    return base


def _make_db(*, project_end, vendors):
    """FakeSupabase for one task/project/trade with the given vendors.

    Project has no coordinates, so the distance stage is skipped. budget is
    None so the bonding stage is skipped. Only insurance varies.
    """
    task = {
        "id": TASK_ID, "name": "Task", "trade_id": TRADE_ID,
        "bid_type": "competitive", "budget_estimate": None, "project_id": PROJECT_ID,
    }
    project = {
        "id": PROJECT_ID, "name": "Project",
        "latitude": None, "longitude": None,
        "estimated_end_date": project_end,
    }

    def _resolve(table, op, _payload):
        if table == "tasks":
            return FakeResponse(task)
        if table == "projects":
            return FakeResponse(project)
        if table == "trades":
            return FakeResponse({"id": TRADE_ID, "name": "Grading"})
        if table == "vendor_trades":
            return FakeResponse([{"vendor_id": v["id"]} for v in vendors])
        if table == "vendors":
            return FakeResponse(vendors)
        # vendor_flags, vendor_contacts, bid_packages
        return FakeResponse([])

    return FakeSupabase(_resolve)


async def _run(*, project_end, vendors):
    db = _make_db(project_end=project_end, vendors=vendors)
    return await filter_qualified_vendors(db=db, task_id=TASK_ID)


def _only(vendors_list):
    assert len(vendors_list) == 1
    return vendors_list[0]


# ── The reported bug ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overdue_project_still_disqualifies_a_truly_expired_vendor():
    """Project ended a month ago (overdue), vendor's insurance expired
    yesterday. Old single-cutoff logic qualified it; it must now be
    disqualified as expired."""
    resp = await _run(project_end=LAST_MONTH, vendors=[_vendor(YESTERDAY)])

    assert resp.total_qualified == 0
    v = _only(resp.disqualified_vendors)
    assert "insurance_expired" in v.disqualification_reasons
    assert v.advisories == []


@pytest.mark.asyncio
async def test_overdue_project_keeps_a_currently_valid_vendor():
    """Same overdue project, but the vendor is insured today → qualified, and
    no spurious lapse advisory (the project horizon is in the past)."""
    resp = await _run(project_end=LAST_MONTH, vendors=[_vendor(NEXT_MONTH)])

    v = _only(resp.qualified_vendors)
    assert v.disqualification_reasons == []
    assert v.advisories == []


# ── The Tier-2 split ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lapses_before_future_end_qualifies_with_an_advisory():
    """Insured today, but the cert ends before the project's future end date:
    still selectable, carries the advisory rather than being excluded."""
    resp = await _run(project_end=NEXT_YEAR, vendors=[_vendor(NEXT_MONTH)])

    assert resp.total_qualified == 1
    v = _only(resp.qualified_vendors)
    assert v.disqualification_reasons == []
    assert "insurance_lapses_before_project_end" in v.advisories


@pytest.mark.asyncio
async def test_coverage_through_project_end_has_no_advisory():
    resp = await _run(project_end=NEXT_MONTH, vendors=[_vendor(NEXT_YEAR)])

    v = _only(resp.qualified_vendors)
    assert v.advisories == []


@pytest.mark.asyncio
async def test_missing_insurance_still_disqualifies():
    resp = await _run(project_end=NEXT_YEAR, vendors=[_vendor(None)])

    assert resp.total_qualified == 0
    v = _only(resp.disqualified_vendors)
    assert "insurance_missing" in v.disqualification_reasons


@pytest.mark.asyncio
async def test_expired_today_disqualifies_even_with_a_future_project():
    resp = await _run(project_end=NEXT_YEAR, vendors=[_vendor(YESTERDAY)])

    v = _only(resp.disqualified_vendors)
    assert "insurance_expired" in v.disqualification_reasons
    # Not double-counted as an advisory.
    assert v.advisories == []
