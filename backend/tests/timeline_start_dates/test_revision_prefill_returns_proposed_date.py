"""Task 8.1.5 — revision prefill carries the vendor's prior proposed_start_date.

Same shape as test_revision_prefill.py — drives the route under a revision
JWT and asserts proposed_start_date is in the response body.
"""

from __future__ import annotations

from uuid import uuid4

from .conftest import (
    PROPOSED_START_ISO,
    SUBMISSION_ID,
    VENDOR_ID,
    vendor_ctx,
)

URL = f"/api/v1/vendor-portal/submissions/{SUBMISSION_ID}/revision-prefill"


def _prefill_spec(*, proposed=PROPOSED_START_ISO) -> dict:
    return {
        "bid_revision_requests": {
            "select": [
                {"id": str(uuid4()), "original_submission_id": str(SUBMISSION_ID)}
            ]
        },
        "bid_submissions": {
            "select": [
                {
                    "id": str(SUBMISSION_ID),
                    "vendor_id": str(VENDOR_ID),
                    "vendor_notes": "Prior notes.",
                    "total_amount": "42500.00",
                    "proposed_start_date": proposed,
                }
            ]
        },
        "bid_invitations": {
            "select": {"bid_packages": {"bid_template_id": "tmpl-id"}}
        },
        "bid_template_items": {"select": []},
        "bid_line_items": {"select": []},
        "bid_attachments": {"select": []},
    }


def test_revision_prefill_returns_proposed_start_date(client_factory):
    c = client_factory(_prefill_spec(), ctx=vendor_ctx(revision=True))
    r = c.get(URL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("proposed_start_date") == PROPOSED_START_ISO


def test_revision_prefill_null_proposed_start_date(client_factory):
    c = client_factory(_prefill_spec(proposed=None), ctx=vendor_ctx(revision=True))
    r = c.get(URL)
    assert r.status_code == 200, r.text
    assert r.json().get("proposed_start_date") is None
