"""
Tests for `is_in_use` + `referencing_packages` on the read endpoints.

So the frontend can render the locked-state banner without first
attempting a PUT and catching a 409 round-trip.
"""

from __future__ import annotations

from .conftest import TEMPLATE_ID


def test_get_detail_marks_in_use_when_live_reference_exists(client_live_open):
    client, db = client_live_open

    resp = client.get(f"/api/v1/bid-templates/{TEMPLATE_ID}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_in_use"] is True
    pkgs = body["referencing_packages"]
    assert len(pkgs) == 1
    assert pkgs[0]["task_name"] == "Rough Grading"
    assert pkgs[0]["status"] == "open"
    assert body["referencing_packages_total"] == 1


def test_get_detail_caps_referencing_packages_with_total(client_many_live):
    """Five live packages: array is capped at 3, total reports the true count.

    Without this cap, a heavily-reused template would push thousands of
    rows over the wire on every detail GET. UI only renders one blocker
    plus an overflow count anyway.
    """
    client, db = client_many_live

    resp = client.get(f"/api/v1/bid-templates/{TEMPLATE_ID}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_in_use"] is True
    assert len(body["referencing_packages"]) == 3
    assert body["referencing_packages_total"] == 5


def test_get_detail_marks_not_in_use_when_only_cancelled(client_cancelled_only):
    """Cancelled-only refs do NOT lock the template; flag stays false.

    `referencing_packages` is the LIVE summary; cancelled refs are not
    surfaced here (the delete-message helper carries those separately).
    """
    client, db = client_cancelled_only

    resp = client.get(f"/api/v1/bid-templates/{TEMPLATE_ID}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_in_use"] is False
    assert body["referencing_packages"] == []
    assert body["referencing_packages_total"] == 0


def test_get_detail_marks_not_in_use_when_no_references(client_no_refs):
    client, db = client_no_refs

    resp = client.get(f"/api/v1/bid-templates/{TEMPLATE_ID}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_in_use"] is False
    assert body["referencing_packages"] == []
    assert body["referencing_packages_total"] == 0


def test_list_rows_carry_in_use_flag(client_live_open):
    client, db = client_live_open

    resp = client.get("/api/v1/bid-templates")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    # The mock returns the same source template row for the list select,
    # so we expect at least one item with is_in_use set.
    assert any(item.get("is_in_use") is True for item in body["items"])
