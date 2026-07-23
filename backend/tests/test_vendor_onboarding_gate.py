"""
Two rules that keep vendor eligibility honest.

1. insurance_expiration_date is derived, not input. It mirrors
   MAX(expiration_date) over the vendor's valid insurance certificates and is
   recomputed on every document upload and delete. Accepting it from a request
   body let a PM claim coverage no certificate backs, which turns the pre-award
   "uninsurable liability" BLOCK into a PASS, and the typed value was silently
   overwritten by the next document change anyway.

2. onboarding_status='complete' is gated. It is a hard eligibility gate in
   vendor_filtering and half the compliance score in bid_scoring, so a vendor
   marked complete with no address would score 100 there while being invisible
   to the distance filter (no coordinates means the radius check is skipped).
"""

from datetime import date, timedelta
from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import get_current_active_user
from app.core.supabase_client import get_supabase
from app.services.vendor_service import missing_requirements_for_complete
from tests._fakes import FakeResponse, FakeSupabase


_NOW = "2026-01-01T00:00:00+00:00"
FAKE_USER = {
    "user_id": str(uuid4()),
    "email": "pm@bluonx.dev",
    "full_name": "Test PM",
    "role": "project_manager",
    "is_active": True,
}

FUTURE = (date.today() + timedelta(days=365)).isoformat()
PAST = (date.today() - timedelta(days=30)).isoformat()


def _vendor_row(**overrides) -> dict:
    base = {
        "id": str(uuid4()),
        "company_name": "Row Vendor",
        "address": None, "city": None, "state": None, "zip_code": None,
        "latitude": None, "longitude": None,
        "insurance_expiration_date": None,
        "insurance_coverage_amount": None,
        "bonding_capacity": None,
        "max_active_jobs": None,
        "current_active_jobs": 0,
        "onboarding_status": "pending",
        "status": "active",
        "notes": None,
        "created_at": _NOW, "updated_at": _NOW, "deleted_at": None,
    }
    base.update(overrides)
    return base


def _contact_row(**overrides) -> dict:
    base = {
        "id": str(uuid4()), "vendor_id": str(uuid4()),
        "full_name": "C", "email": "c@x.com", "phone": None, "title": None,
        "is_primary": True, "created_at": _NOW, "updated_at": _NOW,
    }
    base.update(overrides)
    return base


def _resolver(mapping):
    def _resolve(table, op, payload):
        value = mapping.get((table, op))
        if callable(value):
            return value(payload)
        if value is not None:
            return value
        return FakeResponse([])
    return _resolve


@pytest.fixture()
def make_client():
    def _make(mapping):
        app.dependency_overrides[get_current_active_user] = lambda: FAKE_USER
        app.dependency_overrides[get_supabase] = lambda: FakeSupabase(_resolver(mapping))
        return TestClient(app)
    yield _make
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _no_geocoding():
    """Keep geocoding out of these tests; it has its own suite."""
    with patch("app.services.geocoding.settings.GOOGLE_MAPS_API_KEY", None):
        yield


def _existing(**overrides):
    vid = overrides.pop("id", str(uuid4()))
    row = _vendor_row(id=vid, **overrides)
    return vid, {
        ("vendors", "select"): FakeResponse(row),
        ("vendors", "update"): lambda p: FakeResponse([{**row, **p}]),
    }


# ── The helper, in isolation ───────────────────────────────────────────────


class TestMissingRequirements:
    def test_bare_vendor_is_missing_both(self):
        missing = missing_requirements_for_complete(_vendor_row())
        assert len(missing) == 2

    def test_any_single_address_field_satisfies_the_address_rule(self):
        """Not the street line specifically: geocoding joins whatever is
        present, so "Austin, TX" is locatable while a bare street line is not."""
        for field in ("address", "city", "state", "zip_code"):
            missing = missing_requirements_for_complete(
                _vendor_row(**{field: "Austin"}, insurance_expiration_date=FUTURE)
            )
            assert missing == [], f"{field} alone should satisfy the address rule"

    def test_whitespace_only_address_does_not_count(self):
        missing = missing_requirements_for_complete(
            _vendor_row(city="   ", insurance_expiration_date=FUTURE)
        )
        assert any("address" in m for m in missing)

    def test_expired_certificate_is_reported_separately_from_a_missing_one(self):
        expired = missing_requirements_for_complete(
            _vendor_row(city="Austin", insurance_expiration_date=PAST)
        )
        absent = missing_requirements_for_complete(_vendor_row(city="Austin"))
        assert expired != absent
        assert PAST in expired[0]

    def test_certificate_expiring_today_still_counts_as_valid(self):
        missing = missing_requirements_for_complete(
            _vendor_row(city="Austin", insurance_expiration_date=date.today().isoformat())
        )
        assert missing == []

    def test_fully_qualified_vendor_has_nothing_missing(self):
        assert missing_requirements_for_complete(
            _vendor_row(address="1 Main St", city="Austin", insurance_expiration_date=FUTURE)
        ) == []


# ── Create ─────────────────────────────────────────────────────────────────


class TestCreate:
    def _payload(self, **overrides):
        base = {
            "company_name": "New Vendor",
            "contacts": [{"full_name": "A", "email": "a@x.com", "is_primary": True}],
        }
        base.update(overrides)
        return base

    def test_cannot_create_a_vendor_already_marked_complete(self, make_client):
        """No insurance certificate can exist before the vendor row does, so
        'complete' is not an available value at create time."""
        client = make_client({
            ("vendors", "insert"): lambda p: FakeResponse([_vendor_row(**p)]),
            ("vendor_contacts", "insert"): lambda p: FakeResponse([_contact_row(**p)]),
        })
        resp = client.post("/api/v1/vendors", json=self._payload(onboarding_status="complete"))
        assert resp.status_code == 422, resp.text

    @pytest.mark.parametrize("value", ["pending", "partial"])
    def test_pending_and_partial_are_accepted(self, make_client, value):
        client = make_client({
            ("vendors", "insert"): lambda p: FakeResponse([_vendor_row(**p)]),
            ("vendor_contacts", "insert"): lambda p: FakeResponse([_contact_row(**p)]),
        })
        resp = client.post("/api/v1/vendors", json=self._payload(onboarding_status=value))
        assert resp.status_code == 201, resp.text

    def test_insurance_expiration_in_the_body_is_not_stored(self, make_client):
        """The field is derived. A client-supplied value would claim coverage
        no certificate backs."""
        captured = {}

        def _capture(payload):
            captured.update(payload)
            return FakeResponse([_vendor_row(**payload)])

        client = make_client({
            ("vendors", "insert"): _capture,
            ("vendor_contacts", "insert"): lambda p: FakeResponse([_contact_row(**p)]),
        })
        resp = client.post(
            "/api/v1/vendors",
            json=self._payload(insurance_expiration_date=FUTURE),
        )
        assert resp.status_code == 201, resp.text
        assert "insurance_expiration_date" not in captured


# ── Update: the promotion gate ─────────────────────────────────────────────


class TestUpdateGate:
    def test_blocked_with_no_address_and_no_insurance(self, make_client):
        vid, mapping = _existing()
        resp = make_client(mapping).patch(
            f"/api/v1/vendors/{vid}", json={"onboarding_status": "complete"}
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"].lower()
        assert "address" in detail and "insurance" in detail

    def test_blocked_with_an_address_but_no_insurance(self, make_client):
        vid, mapping = _existing(city="Austin", state="TX")
        resp = make_client(mapping).patch(
            f"/api/v1/vendors/{vid}", json={"onboarding_status": "complete"}
        )
        assert resp.status_code == 409, resp.text
        assert "insurance" in resp.json()["detail"].lower()

    def test_blocked_when_the_certificate_on_file_has_expired(self, make_client):
        vid, mapping = _existing(city="Austin", insurance_expiration_date=PAST)
        resp = make_client(mapping).patch(
            f"/api/v1/vendors/{vid}", json={"onboarding_status": "complete"}
        )
        assert resp.status_code == 409, resp.text
        assert "expired" in resp.json()["detail"].lower()

    def test_allowed_when_both_requirements_are_met(self, make_client):
        vid, mapping = _existing(city="Austin", insurance_expiration_date=FUTURE)
        resp = make_client(mapping).patch(
            f"/api/v1/vendors/{vid}", json={"onboarding_status": "complete"}
        )
        assert resp.status_code == 200, resp.text

    def test_address_supplied_in_the_same_patch_counts(self, make_client):
        """The gate reads the row as it will be after the update, so supplying
        the missing address and promoting in one call works."""
        vid, mapping = _existing(insurance_expiration_date=FUTURE)
        resp = make_client(mapping).patch(
            f"/api/v1/vendors/{vid}",
            json={"city": "Austin", "onboarding_status": "complete"},
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize("value", ["pending", "partial"])
    def test_other_statuses_are_never_gated(self, make_client, value):
        vid, mapping = _existing()
        resp = make_client(mapping).patch(
            f"/api/v1/vendors/{vid}", json={"onboarding_status": value}
        )
        assert resp.status_code == 200, resp.text

    def test_unrelated_edits_to_an_incomplete_vendor_are_not_gated(self, make_client):
        """The gate fires on the transition only, so editing a vendor that
        happens to be incomplete keeps working."""
        vid, mapping = _existing()
        resp = make_client(mapping).patch(
            f"/api/v1/vendors/{vid}", json={"company_name": "Renamed"}
        )
        assert resp.status_code == 200, resp.text

    def test_insurance_expiration_in_the_body_is_not_stored(self, make_client):
        captured = {}
        vid = str(uuid4())
        row = _vendor_row(id=vid)

        def _capture(payload):
            captured.update(payload)
            return FakeResponse([{**row, **payload}])

        client = make_client({
            ("vendors", "select"): FakeResponse(row),
            ("vendors", "update"): _capture,
        })
        resp = client.patch(
            f"/api/v1/vendors/{vid}",
            json={"company_name": "Renamed", "insurance_expiration_date": FUTURE},
        )
        assert resp.status_code == 200, resp.text
        assert "insurance_expiration_date" not in captured
