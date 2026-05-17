"""
Step 3 C.2 — GET /vendor-portal/submissions/{id}/revision-prefill.

Revision-only endpoint: requires a revision JWT AND the path
submission_id must equal the revision request's original_submission_id
AND the JWT vendor must own the submission.
"""

from __future__ import annotations

from uuid import uuid4

from .conftest import (
    OTHER_VENDOR_ID,
    SUBMISSION_ID,
    VENDOR_ID,
    line_item_rows,
    template_item_rows,
    vendor_ctx,
)

URL = f"/api/v1/vendor-portal/submissions/{SUBMISSION_ID}/revision-prefill"


def _prefill_spec(*, rr_original=None, sub_vendor=None) -> dict:
    return {
        "bid_revision_requests": {
            "select": [
                {
                    "id": str(uuid4()),
                    "original_submission_id": rr_original or str(SUBMISSION_ID),
                }
            ]
        },
        "bid_submissions": {
            "select": [
                {
                    "id": str(SUBMISSION_ID),
                    "vendor_id": sub_vendor or str(VENDOR_ID),
                    "vendor_notes": "Original notes.",
                    "total_amount": "42500.00",
                }
            ]
        },
        "bid_invitations": {
            "select": {"bid_packages": {"bid_template_id": "tmpl-id"}}
        },
        "bid_template_items": {"select": template_item_rows()},
        "bid_line_items": {"select": line_item_rows()},
        "bid_attachments": {"select": [{"id": str(uuid4())}]},
    }


def test_prefill_happy_path(client_factory):
    c = client_factory(_prefill_spec(), ctx=vendor_ctx(revision=True))
    r = c.get(URL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_amount"] == "42500.00"
    assert body["vendor_notes"] == "Original notes."
    assert len(body["line_items"]) == 2
    assert all(li["template_item_id"] for li in body["line_items"])
    assert body["line_items"][0]["description"] == "Site prep"
    assert len(body["attachment_ids"]) == 1


def test_prefill_non_revision_jwt_403(client_factory):
    c = client_factory(_prefill_spec(), ctx=vendor_ctx(revision=False))
    r = c.get(URL)
    assert r.status_code == 403


def test_prefill_submission_mismatch_403(client_factory):
    c = client_factory(
        _prefill_spec(rr_original=str(uuid4())), ctx=vendor_ctx(revision=True)
    )
    r = c.get(URL)
    assert r.status_code == 403


def test_prefill_vendor_mismatch_403(client_factory):
    c = client_factory(
        _prefill_spec(sub_vendor=str(OTHER_VENDOR_ID)),
        ctx=vendor_ctx(revision=True),
    )
    r = c.get(URL)
    assert r.status_code == 403


def test_prefill_revision_request_missing_404(client_factory):
    spec = _prefill_spec()
    spec["bid_revision_requests"]["select"] = []
    c = client_factory(spec, ctx=vendor_ctx(revision=True))
    r = c.get(URL)
    assert r.status_code == 404


def test_prefill_orphan_line_item_skipped(client_factory):
    spec = _prefill_spec()
    orphan = dict(line_item_rows()[0])
    orphan["sort_order"] = 99  # not in template map
    spec["bid_line_items"]["select"] = [orphan, line_item_rows()[1]]
    c = client_factory(spec, ctx=vendor_ctx(revision=True))
    r = c.get(URL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["line_items"]) == 1  # orphan skipped, second kept
    assert body["line_items"][0]["sort_order"] == 1
