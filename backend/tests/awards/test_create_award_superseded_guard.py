"""
Step 3 — award guard. create_award rejects a superseded submission
with 409 BEFORE any (future) side effects; otherwise the existing 501
stub behavior is unchanged.
"""

from __future__ import annotations

from .conftest import SUBMISSION_ID, award_body

URL = "/api/v1/awards"


def test_create_award_superseded_returns_409(client_factory):
    c = client_factory(
        {"bid_submissions": {"select": [{"id": str(SUBMISSION_ID), "is_superseded": True}]}}
    )
    r = c.post(URL, json=award_body())
    assert r.status_code == 409
    assert r.json()["detail"] == (
        "This submission has been revised. Award the latest version instead."
    )


def test_create_award_non_superseded_still_501(client_factory):
    c = client_factory(
        {"bid_submissions": {"select": [{"id": str(SUBMISSION_ID), "is_superseded": False}]}}
    )
    r = c.post(URL, json=award_body())
    assert r.status_code == 501


def test_create_award_submission_absent_still_501(client_factory):
    c = client_factory({"bid_submissions": {"select": []}})
    r = c.post(URL, json=award_body())
    assert r.status_code == 501
