"""Task 8.1.5 — GET /vendor-portal/bid-context returns desired_start_date
on bid_package."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .conftest import (
    BID_PACKAGE_ID,
    DESIRED_START_ISO,
    INVITATION_ID,
    VENDOR_CONTACT_ID,
    VENDOR_ID,
    _future_dt,
    vendor_ctx,
)

URL = "/api/v1/vendor-portal/bid-context"


def _invitation_tree(*, desired=DESIRED_START_ISO) -> dict:
    """Shape returned by _fetch_invitation_tree (single joined SELECT)."""
    return {
        "id": str(INVITATION_ID),
        "vendor_id": str(VENDOR_ID),
        "vendor_contact_id": str(VENDOR_CONTACT_ID),
        "bid_package_id": str(BID_PACKAGE_ID),
        "vendors": {"id": str(VENDOR_ID), "company_name": "Apex"},
        "vendor_contacts": {
            "id": str(VENDOR_CONTACT_ID),
            "full_name": "Jane",
            "email": "jane@a.example",
            "phone": None,
        },
        "bid_packages": {
            "id": str(BID_PACKAGE_ID),
            "round_number": 1,
            "deadline": _future_dt(),
            "instructions": "",
            "bid_template_id": str(uuid4()),
            "task_id": str(uuid4()),
            "desired_start_date": desired,
            "tasks": {
                "id": str(uuid4()),
                "name": "Mass Grading",
                "description": "",
                "projects": {
                    "id": str(uuid4()),
                    "name": "North Yard",
                    "city": "Austin",
                    "address": "1 Main St",
                },
                "trades": {"id": str(uuid4()), "name": "Earthwork"},
            },
            "bid_templates": {
                "id": str(uuid4()),
                "name": "Standard",
                "is_lump_sum": True,
            },
        },
    }


def _spec(*, desired=DESIRED_START_ISO) -> dict:
    return {
        "bid_invitations": {"select": _invitation_tree(desired=desired)},
        "bid_template_items": {"select": []},
        "bid_package_documents": {"select": []},
        "bid_submissions": {"select": []},
    }


def test_bid_context_includes_desired_start_date(client_factory):
    c = client_factory(_spec(), ctx=vendor_ctx(revision=False))
    r = c.get(URL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bid_package"]["desired_start_date"] == DESIRED_START_ISO


def test_bid_context_null_desired_start_date(client_factory):
    c = client_factory(_spec(desired=None), ctx=vendor_ctx(revision=False))
    r = c.get(URL)
    assert r.status_code == 200, r.text
    assert r.json()["bid_package"]["desired_start_date"] is None
